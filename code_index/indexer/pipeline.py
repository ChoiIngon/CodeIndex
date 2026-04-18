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
    fpath, chunk_cfg = args
    try:
        from code_index.indexer.chunker import chunk_file
        chunks = chunk_file(fpath, chunk_cfg)
        sha   = file_sha256(fpath)
        mtime = os.path.getmtime(fpath)
        return fpath, chunks, sha, mtime, None
    except Exception as e:
        return fpath, [], "", 0.0, str(e)


# ── 메인 인덱싱 ───────────────────────────────────────────────────────────────

def run_index(cfg: Optional[dict] = None) -> None:
    if cfg is None:
        cfg = load_config()

    idx_cfg   = cfg["indexer"]
    emb_cfg   = cfg["embedding"]
    vs_cfg    = cfg["vector_store"]
    model_cfg = cfg["models"]

    data_dir   = vs_cfg.get("data_path", "./data/qdrant")
    meta_path  = os.path.join(os.path.dirname(data_dir), "metadata.db")
    cache_path = os.path.join(os.path.dirname(data_dir), "embed_cache.db")

    metadata     = MetadataStore(meta_path)
    cache        = EmbedCache(cache_path)
    vector_store = VectorStore(vs_cfg, emb_cfg["vector_size"])

    embed_model_path = resolve_model(model_cfg["embed"], model_cfg.get("cache_dir", ""))
    embedder = Embedder(embed_model_path, emb_cfg, cache)

    source_paths = idx_cfg["source_paths"]
    extensions   = idx_cfg["extensions"]
    exclude      = idx_cfg.get("exclude_patterns", [])

    print("[Pipeline] 파일 목록 수집 중...", file=sys.stderr)
    t0 = time.time()
    current_files = list(scan_files(source_paths, extensions, exclude))
    print(f"[Pipeline] 파일 {len(current_files)}개 발견 ({time.time()-t0:.1f}s)", file=sys.stderr)

    new_files, modified_files, deleted_files = detect_changes(current_files, metadata)
    print(
        f"[Pipeline] 신규={len(new_files)}, 수정={len(modified_files)}, 삭제={len(deleted_files)}",
        file=sys.stderr,
    )

    for fpath in deleted_files:
        _delete_file(fpath, metadata, vector_store)

    to_index = new_files + modified_files
    if not to_index:
        print("[Pipeline] 변경 없음. 인덱싱 스킵.", file=sys.stderr)
        metadata.close()
        cache.close()
        return

    for fpath in modified_files:
        _delete_file(fpath, metadata, vector_store)

    batch_size = emb_cfg.get("batch_size", 32)
    chunk_cfg  = {
        "chunk_min_lines":    idx_cfg.get("chunk_min_lines", 5),
        "chunk_max_lines":    idx_cfg.get("chunk_max_lines", 150),
        "chunk_overlap_lines": idx_cfg.get("chunk_overlap_lines", 10),
    }

    cpu_count   = os.cpu_count() or 4
    cfg_workers = idx_cfg.get("chunk_workers", 0)
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
                pool.submit(_chunk_worker, (fpath, chunk_cfg)): fpath
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
    stats = metadata.stats()
    print(
        f"[Pipeline] 완료. {total}개 파일 / {stats['total_chunks']}개 청크 "
        f"({t_total:.1f}s, 평균 {total/t_total:.1f}파일/s)",
        file=sys.stderr,
    )

    metadata.close()
    cache.close()


def _delete_file(fpath: str, metadata: MetadataStore, vector_store: VectorStore) -> None:
    chunk_ids = metadata.get_chunk_ids_for_file(fpath)
    if chunk_ids:
        vector_store.delete(chunk_ids)
    metadata.delete_file(fpath)
