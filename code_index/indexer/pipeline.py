from __future__ import annotations

import os
import queue
import sys
import threading
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Optional

from ..config import load_config
from ..models.model_manager import resolve_model
from ..store.cache import EmbedCache
from ..store.metadata_store import MetadataStore
from ..store.vector_store import VectorStore
from .embedder import Embedder
from .scanner import detect_changes, file_sha256, scan_files


# ── 병렬 청킹 워커 (module-level: Windows spawn 방식에서 pickle 가능) ────────────

def _chunk_worker(args: tuple) -> tuple:
    """별도 프로세스에서 파일 하나를 청킹하고 (fpath, chunks, sha, mtime, err) 반환."""
    fpath, chunk_cfg, project_name = args
    try:
        from code_index.indexer.chunker import chunk_file
        chunks = chunk_file(fpath, chunk_cfg, project_name)
        sha   = file_sha256(fpath)
        mtime = os.path.getmtime(fpath)
        return fpath, chunks, sha, mtime, None
    except Exception as e:
        return fpath, [], "", 0.0, str(e)


# ── 메인 인덱싱 ───────────────────────────────────────────────────────────────

def run_index(cfg: Optional[dict] = None) -> None:
    if cfg is None:
        from ..config import load_config
        cfg = load_config()

    from ..config import get_all_projects

    emb_cfg   = cfg["embedding"]
    vs_cfg    = cfg["vector_store"]
    model_cfg = cfg["models"]
    indexer_cfg = cfg["indexer"]  # indexer 레벨 설정

    data_dir   = vs_cfg.get("data_path", "./data/qdrant")
    meta_path  = os.path.join(os.path.dirname(data_dir), "metadata.db")
    cache_path = os.path.join(os.path.dirname(data_dir), "embed_cache.db")

    metadata     = MetadataStore(meta_path)
    cache        = EmbedCache(cache_path)
    vector_store = VectorStore(vs_cfg, emb_cfg["vector_size"])

    embed_model_path = resolve_model(model_cfg["embed"], model_cfg.get("cache_dir", ""))
    embedder = Embedder(embed_model_path, emb_cfg, cache)

    # 프로젝트별 설정 가져오기
    projects = get_all_projects(cfg)
    
    # 삭제된 프로젝트 감지 및 정리
    _cleanup_deleted_projects(projects, metadata, vector_store)
    
    print(f"[Pipeline] {len(projects)}개 프로젝트 인덱싱 시작...", file=sys.stderr)
    
    for project_name, project_cfg in projects.items():
        print(f"\n[Pipeline] === 프로젝트: {project_name} ===", file=sys.stderr)
        _run_project_index(project_name, project_cfg, indexer_cfg, metadata, cache, vector_store, embedder, emb_cfg)
    
    metadata.close()
    cache.close()


def _run_project_index(project_name: str, project_cfg: dict, indexer_cfg: dict, metadata, cache, vector_store, embedder, emb_cfg) -> None:
    """단일 프로젝트 인덱싱 처리."""
    source_paths = project_cfg["source_paths"]
    extensions   = project_cfg["extensions"]
    exclude      = project_cfg.get("exclude_patterns", [])

    print("[Pipeline] 파일 목록 수집 중...", file=sys.stderr)
    t0 = time.time()
    current_files = list(scan_files(source_paths, extensions, exclude))
    print(f"[Pipeline] 파일 {len(current_files)}개 발견 ({time.time()-t0:.1f}s)", file=sys.stderr)

    new_files, modified_files, deleted_files = detect_changes(current_files, metadata, source_paths, project_name)
    print(
        f"[Pipeline] 신규={len(new_files)}, 수정={len(modified_files)}, 삭제={len(deleted_files)}",
        file=sys.stderr,
    )

    # 대량 삭제 최적화
    if deleted_files:
        _delete_files_batch(deleted_files, metadata, vector_store)

    to_index = new_files + modified_files
    if not to_index:
        print("[Pipeline] 변경 없음. 인덱싱 스킵.", file=sys.stderr)
        return

    for fpath in modified_files:
        _delete_file(fpath, metadata, vector_store)

    batch_size = emb_cfg.get("batch_size", 32)
    chunk_cfg  = {
        "chunk_min_lines":    indexer_cfg.get("chunk_min_lines", 5),
        "chunk_max_lines":    indexer_cfg.get("chunk_max_lines", 150),
        "chunk_overlap_lines": indexer_cfg.get("chunk_overlap_lines", 10),
    }

    cpu_count   = os.cpu_count() or 4
    cfg_workers = indexer_cfg.get("chunk_workers", 0)
    workers     = cfg_workers if cfg_workers > 0 else max(1, cpu_count // 2)
    total       = len(to_index)

    print(
        f"[Pipeline] 청킹+임베딩 파이프라인 시작 "
        f"(청킹 워커={workers}, 임베딩 배치={batch_size}, 파일={total}개)...",
        file=sys.stderr,
    )
    t_start = time.time()

    # ── 청킹 결과를 흘려보내는 큐 ────────────────────────────────────────────
    # maxsize 를 크게 잡아 back-pressure 로 인한 producer 블록 최소화
    result_q: queue.Queue = queue.Queue(maxsize=workers * 64)
    _SENTINEL = object()

    # ── 프로듀서 스레드: ProcessPoolExecutor 로 병렬 청킹 ──────────────────────
    chunked_produced = [0]  # 청킹 완료 카운트 (producer 기준)
    chunked_count    = [0]  # 소비 카운트 (consumer 기준)
    embed_batches         = [0]
    total_chunks_embedded = [0]
    _producer_done   = threading.Event()

    def _producer() -> None:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_chunk_worker, (fpath, chunk_cfg, project_name)): fpath
                for fpath in to_index
            }
            for future in as_completed(futures):
                chunked_produced[0] += 1
                result_q.put(future.result())
        result_q.put(_SENTINEL)
        _producer_done.set()

    # ── 진행률 출력 스레드: 0.5초마다 \r 덮어쓰기 ────────────────────────────
    def _progress_reporter() -> None:
        while not _producer_done.is_set():
            elapsed = time.time() - t_start
            produced = chunked_produced[0]
            consumed = chunked_count[0]
            embedded = total_chunks_embedded
            rate = produced / elapsed if elapsed > 0 else 0
            pct  = produced * 100 // total if total else 0
            print(
                f"\r[청킹] {produced}/{total} ({pct}%)  "
                f"임베딩={consumed}파일/{embedded}청크  "
                f"{rate:.1f}파일/s  {elapsed:.0f}s",
                end="",
                file=sys.stderr,
                flush=True,
            )
            _producer_done.wait(timeout=0.5)
        # 완료 후 줄바꿈
        print(file=sys.stderr)

    producer_thread  = threading.Thread(target=_producer,          daemon=True)
    progress_thread  = threading.Thread(target=_progress_reporter, daemon=True)
    producer_thread.start()
    progress_thread.start()

    # ── 컨슈머 (메인 스레드): 임베딩 + upsert ────────────────────────────────
    embed_buffer: list = []
    file_meta: dict    = {}   # fpath -> (sha, mtime)

    def _flush(force: bool = False) -> None:
        while len(embed_buffer) >= batch_size or (force and embed_buffer):
            batch  = embed_buffer[:batch_size]
            del embed_buffer[:batch_size]
            texts  = [c.content for c in batch]
            hashes = [c.content_hash for c in batch]
            vecs   = embedder.embed_batch(texts, hashes)
            if len(vecs) == len(batch):
                vector_store.upsert_batch(batch, vecs)
                metadata.upsert_chunks(batch)
            embed_batches[0]         += 1
            total_chunks_embedded[0] += len(batch)

    # 진행률 로깅 (500파일마다 또는 완료 시)
    LOG_INTERVAL = 500

    while True:
        item = result_q.get()
        if item is _SENTINEL:
            break

        fpath, chunks, sha, mtime, err = item
        chunked_count[0] += 1
        n = chunked_count[0]

        if n % LOG_INTERVAL == 0 or n == total:
            elapsed = time.time() - t_start
            files_s  = n / elapsed if elapsed > 0 else 0
            print(
                f"[Pipeline] 청킹(완료/소비)={chunked_produced[0]}/{n}/{total}  "
                f"임베딩 배치={embed_batches[0]}  청크={total_chunks_embedded[0]}  "
                f"({elapsed:.0f}s, {files_s:.1f}파일/s)",
                file=sys.stderr,
            )

        if err:
            print(f"[Pipeline] 오류 {fpath}: {err}", file=sys.stderr)

        if not chunks:
            if sha:
                metadata.upsert_file(fpath, sha, mtime)
            continue

        embed_buffer.extend(chunks)
        file_meta[fpath] = (sha, mtime)
        _flush()

    producer_thread.join()
    progress_thread.join()

    # 버퍼 잔량 임베딩
    _flush(force=True)

    # 파일 메타 일괄 업데이트
    for fpath, (sha, mtime) in file_meta.items():
        metadata.upsert_file(fpath, sha, mtime)

    t_total = time.time() - t_start
    print(
        f"[Pipeline] 프로젝트 완료. {total}개 파일 "
        f"({t_total:.1f}s, 평균 {total/t_total:.1f}파일/s)",
        file=sys.stderr,
    )


def _delete_files_batch(fpaths: list[str], metadata: MetadataStore, vector_store: VectorStore) -> None:
    """대량 파일 삭제를 배치로 최적화하여 처리."""
    total = len(fpaths)
    if total == 0:
        return
        
    print(f"[Pipeline] 삭제 작업 시작... {total}개 파일", file=sys.stderr)
    t_start = time.time()
    
    # 1. 모든 삭제 대상 파일의 chunk_ids 수집 (배치로)
    print("[Pipeline] 삭제 대상 청크 ID 수집 중...", file=sys.stderr)
    all_chunk_ids = []
    chunk_collection_time = time.time()
    
    # 배치 크기로 나누어서 메모리 사용량 관리
    BATCH_SIZE = 1000
    for i in range(0, total, BATCH_SIZE):
        batch_fpaths = fpaths[i:i+BATCH_SIZE]
        
        # 배치별 청크 ID 수집
        for fpath in batch_fpaths:
            chunk_ids = metadata.get_chunk_ids_for_file(fpath)
            all_chunk_ids.extend(chunk_ids)
            
        # 진행상황 표시
        processed = min(i + BATCH_SIZE, total)
        if processed % 5000 == 0 or processed == total:
            elapsed = time.time() - chunk_collection_time
            rate = processed / elapsed if elapsed > 0 else 0
            print(f"[Pipeline] 청크 ID 수집: {processed}/{total} ({processed*100//total}%) - {rate:.1f}파일/s", 
                  file=sys.stderr)
    
    print(f"[Pipeline] 총 {len(all_chunk_ids)}개 청크 삭제 예정", file=sys.stderr)
    
    # 2. 벡터 스토어에서 모든 청크를 한 번에 삭제
    if all_chunk_ids:
        print("[Pipeline] 벡터 스토어에서 청크 삭제 중...", file=sys.stderr)
        # 청크가 너무 많으면 배치로 나누어 삭제
        VECTOR_BATCH_SIZE = 10000
        for i in range(0, len(all_chunk_ids), VECTOR_BATCH_SIZE):
            batch_chunk_ids = all_chunk_ids[i:i+VECTOR_BATCH_SIZE]
            vector_store.delete(batch_chunk_ids)
            
            processed_chunks = min(i + VECTOR_BATCH_SIZE, len(all_chunk_ids))
            if len(all_chunk_ids) > VECTOR_BATCH_SIZE:
                print(f"[Pipeline] 벡터 삭제 진행: {processed_chunks}/{len(all_chunk_ids)} 청크", file=sys.stderr)
    
    # 3. 메타데이터에서 파일들을 배치로 삭제
    print("[Pipeline] 메타데이터에서 파일 정보 삭제 중...", file=sys.stderr)
    metadata._delete_files_batch(fpaths)
    
    elapsed = time.time() - t_start
    rate = total / elapsed if elapsed > 0 else 0
    print(f"[Pipeline] 삭제 완료: {total}개 파일, {len(all_chunk_ids)}개 청크 ({elapsed:.1f}s, {rate:.1f}파일/s)", 
          file=sys.stderr)


def _delete_file(fpath: str, metadata: MetadataStore, vector_store: VectorStore) -> None:
    chunk_ids = metadata.get_chunk_ids_for_file(fpath)
    if chunk_ids:
        vector_store.delete(chunk_ids)
    metadata.delete_file(fpath)


def _cleanup_deleted_projects(current_projects: dict, metadata: MetadataStore, vector_store: VectorStore) -> None:
    """settings.json에서 삭제된 프로젝트의 모든 데이터를 정리."""
    try:
        # 현재 설정에 있는 프로젝트 이름들
        current_project_names = set(current_projects.keys())
        
        # 데이터베이스에서 모든 프로젝트 이름 조회
        existing_project_names = set()
        rows = metadata._con.execute("SELECT DISTINCT project_name FROM chunks WHERE project_name != ''").fetchall()
        for row in rows:
            if row[0]:  # 빈 문자열 제외
                existing_project_names.add(row[0])
        
        # 삭제된 프로젝트 식별
        deleted_projects = existing_project_names - current_project_names
        
        if deleted_projects:
            print(f"[Pipeline] 삭제된 프로젝트 발견: {list(deleted_projects)}", file=sys.stderr)
            
            for project_name in deleted_projects:
                print(f"[Pipeline] 프로젝트 '{project_name}' 데이터 정리 중...", file=sys.stderr)
                t_start = time.time()
                
                # 메타데이터에서 프로젝트 삭제
                result = metadata.delete_project(project_name)
                
                # 벡터 스토어에서 해당 청크들 삭제
                if result["chunk_ids"]:
                    vector_store.delete(result["chunk_ids"])
                
                elapsed = time.time() - t_start
                print(f"[Pipeline] 프로젝트 '{project_name}' 정리 완료: "
                      f"{result['deleted_files']}개 파일, {result['deleted_chunks']}개 청크 "
                      f"({elapsed:.1f}s)", file=sys.stderr)
        else:
            print("[Pipeline] 삭제된 프로젝트 없음", file=sys.stderr)
            
    except Exception as e:
        print(f"[Pipeline] 프로젝트 정리 중 오류: {e}", file=sys.stderr)
