from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..store.metadata_store import ChunkMeta, MetadataStore
from ..store.vector_store import VectorStore


@dataclass
class SearchResult:
    chunk_id: str
    score: float
    file_path: str
    language: str
    start_line: int
    end_line: int
    symbol_type: str
    symbol_name: str
    parent_class: str
    namespace: str
    content: str
    project_name: str = ""


def hybrid_search(
    query_vec: list[float],
    query_text: str,
    metadata: MetadataStore,
    vector_store: VectorStore,
    top_k: int = 20,
    alpha: float = 0.7,
    filters: Optional[dict] = None,
) -> list[SearchResult]:
    """Dense HNSW + BM25 FTS5 하이브리드 검색, RRF 퓨전."""
    # Dense 검색
    dense_hits = vector_store.search(query_vec, top_k=top_k * 2, filter_dict=filters)
    dense_ids = [h.chunk_id for h in dense_hits]

    # BM25 검색 (FTS5)
    bm25_hits = _safe_bm25(metadata, query_text, top_k * 2, filters)
    bm25_ids = [h[0] for h in bm25_hits]

    # RRF 퓨전
    rrf_scores = _rrf_fuse(dense_ids, bm25_ids, alpha=alpha)

    # 상위 top_k 선택 후 메타데이터 조회
    top_ids = sorted(rrf_scores, key=lambda x: rrf_scores[x], reverse=True)[:top_k]
    chunk_map = {c.chunk_id: c for c in metadata.get_chunks_by_ids(top_ids)}

    results: list[SearchResult] = []
    for cid in top_ids:
        chunk = chunk_map.get(cid)
        if not chunk:
            continue
        results.append(SearchResult(
            chunk_id=cid,
            score=rrf_scores[cid],
            file_path=chunk.file_path,
            language=chunk.language,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            symbol_type=chunk.symbol_type,
            symbol_name=chunk.symbol_name,
            parent_class=chunk.parent_class,
            namespace=chunk.namespace,
            content=chunk.content,
            project_name=chunk.project_name,
        ))
    return results


def _safe_bm25(metadata: MetadataStore, query: str, top_k: int, filters: Optional[dict] = None) -> list:
    try:
        return metadata.bm25_search(query, top_k, filters)
    except Exception:
        return []


def _rrf_fuse(dense_ids: list, sparse_ids: list, alpha: float, k: int = 60) -> dict:
    """Reciprocal Rank Fusion. dense weight=alpha, sparse weight=(1-alpha)."""
    scores: dict[str, float] = {}

    for rank, cid in enumerate(dense_ids):
        scores[cid] = scores.get(cid, 0.0) + alpha / (k + rank + 1)

    for rank, cid in enumerate(sparse_ids):
        scores[cid] = scores.get(cid, 0.0) + (1.0 - alpha) / (k + rank + 1)

    return scores
