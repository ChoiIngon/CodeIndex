from __future__ import annotations

import os
import sys
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

    # 수정 파일은 기존 인덱스 먼저 삭제
    modified_set = set(modified_files)
    for fpath in modified_files:
        _delete_file(fpath, metadata, vector_store)

    batch_size = emb_cfg.get("batch_size", 32)
    chunk_cfg  = {
        "chunk_min_lines":    idx_cfg.get("chunk_min_lines", 5),
        "chunk_max_lines":    idx_cfg.get("chunk_max_lines", 150),
        "chunk_overlap_lines": idx_cfg.get("chunk_overlap_lines", 10),
    }

    # 청킹 병렬 워커 수: 0 또는 미설정이면 CPU 절반 자동 사용
    cpu_count = os.cpu_count() or 4
    cfg_workers = idx_cfg.get("chunk_workers", 0)
    workers = cfg_workers if cfg_workers > 0 else max(1, cpu_count // 2)
    total       = len(to_index)

    print(f"[Pipeline] 청킹 시작 (병렬 워커={workers}, 파일={total}개)...", file=sys.stderr)
    t_chunk = time.time()

    # 임베딩 대기 버퍼 (batch_size 단위로 flush)
    embed_buffer: list = []
    file_meta: dict    = {}   # fpath -> (sha, mtime)
    chunked = 0

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

    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_chunk_worker, (fpath, chunk_cfg)): fpath
            for fpath in to_index
        }

        for future in as_completed(futures):
            fpath, chunks, sha, mtime, err = future.result()
            chunked += 1

            if chunked % 500 == 0 or chunked == total:
                elapsed = time.time() - t_chunk
                print(
                    f"[Pipeline] 청킹 {chunked}/{total}  "
                    f"({elapsed:.0f}s, {chunked/elapsed:.0f}파일/s)",
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

    # 버퍼 잔량 임베딩
    _flush(force=True)

    # 파일 메타 일괄 업데이트
    for fpath, (sha, mtime) in file_meta.items():
        metadata.upsert_file(fpath, sha, mtime)

    t_total = time.time() - t0
    stats = metadata.stats()
    print(
        f"[Pipeline] 완료. {total}개 파일 / {stats['total_chunks']}개 청크 "
        f"({t_total:.1f}s)",
        file=sys.stderr,
    )

    metadata.close()
    cache.close()


def _delete_file(fpath: str, metadata: MetadataStore, vector_store: VectorStore) -> None:
    chunk_ids = metadata.get_chunk_ids_for_file(fpath)
    if chunk_ids:
        vector_store.delete(chunk_ids)
    metadata.delete_file(fpath)
