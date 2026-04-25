"""Search code functionality."""

import json
import os
import sys
from pathlib import Path

from code_index import constants
from code_index.config import load_config
from code_index.indexer.embedder import Embedder
from code_index.retriever.hybrid_search import hybrid_search
from code_index.store.cache import EmbedCache
from code_index.store.metadata_store import MetadataStore
from code_index.store.vector_store import VectorStore


def _get_arg(flag: str, default=None):
    """sys.argv 에서 'flag VALUE' 형태의 값을 반환."""
    if flag in sys.argv:
        idx = sys.argv.index(flag)
        if idx + 1 < len(sys.argv):
            return sys.argv[idx + 1]
    return default


def search_code(cfg):
    """Process search code query and output JSON results."""
    
    _query = _get_arg("--search-code")
    if not _query:
        print("[Error] --search-code 다음에 검색어를 입력하세요.", file=sys.stderr)
        sys.exit(1)

    _top_k       = int(_get_arg("--top-k", cfg["search"].get("top_k", 20)))
    _language    = _get_arg("--language", "")
    _symbol_type = _get_arg("--symbol-type", "")
    _project     = _get_arg("--project", "")

    vs_cfg   = cfg["vector_store"]
    emb_cfg  = cfg["embedding"]
    model_cfg = cfg["models"]
    cache_dir = model_cfg.get("cache_dir", "")
    data_dir = vs_cfg.get("data_path", constants.DEFAULT_PATHS["data_dir"])
    meta_path  = os.path.join(os.path.dirname(data_dir), constants.DEFAULT_PATHS["metadata_db"])
    cache_path = os.path.join(os.path.dirname(data_dir), constants.DEFAULT_PATHS["embed_cache_db"])

    from code_index.models.model_manager import resolve_model  # noqa: E402
    
    _metadata     = MetadataStore(meta_path)
    _cache        = EmbedCache(cache_path)
    _vector_store = VectorStore(vs_cfg, emb_cfg["vector_size"])
    _embed_path   = resolve_model(model_cfg["embed"], cache_dir)
    _embedder     = Embedder(_embed_path, emb_cfg, _cache)

    _filters: dict = {}
    if _language:
        _filters["language"] = _language
    if _symbol_type:
        _filters["symbol_type"] = _symbol_type
    if _project:
        _filters["project_name"] = _project

    _vec  = _embedder.embed_query(_query)
    _hits = hybrid_search(
        query_vec=_vec,
        query_text=_query,
        metadata=_metadata,
        vector_store=_vector_store,
        top_k=_top_k,
        alpha=cfg["search"].get("alpha", 0.7),
        filters=_filters or None,
    )
    _result = [
        {
            "chunk_id":    r.chunk_id,
            "score":       round(r.score, 6),
            "file_path":   r.file_path,
            "symbol_name": r.symbol_name,
            "symbol_type": r.symbol_type,
            "start_line":  r.start_line,
            "end_line":    r.end_line,
            "content":     r.content[:1000],
            "project_name": r.project_name,
        }
        for r in _hits
    ]
    sys.stdout.buffer.write(json.dumps(_result, ensure_ascii=False, indent=2).encode("utf-8"))
    sys.stdout.buffer.write(b"\n")
    _metadata.close()
    _cache.close()
    _vector_store.close()
    sys.exit(0)