"""Query batch processing functionality."""

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


def query_batch(cfg):
    """Process batch queries from stdin and output JSON results."""
    
    # --top-k 파싱
    _top_k = cfg["search"].get("top_k", 20)
    if "--top-k" in sys.argv:
        _top_k = int(sys.argv[sys.argv.index("--top-k") + 1])

    vs_cfg  = cfg["vector_store"]
    emb_cfg = cfg["embedding"]
    model_cfg = cfg["models"]
    cache_dir = model_cfg.get("cache_dir", "")
    data_dir  = vs_cfg.get("data_path", constants.DEFAULT_PATHS["data_dir"])
    meta_path  = os.path.join(os.path.dirname(data_dir), constants.DEFAULT_PATHS["metadata_db"])
    cache_path = os.path.join(os.path.dirname(data_dir), constants.DEFAULT_PATHS["embed_cache_db"])

    from code_index.models.model_manager import resolve_model  # noqa: E402
    
    _metadata     = MetadataStore(meta_path)
    _cache        = EmbedCache(cache_path)
    _vector_store = VectorStore(vs_cfg, emb_cfg["vector_size"])
    _embed_path   = resolve_model(model_cfg["embed"], cache_dir)
    _embedder     = Embedder(_embed_path, emb_cfg, _cache)

    # Windows에서 sys.stdin 기본 인코딩(cp949)으로 UTF-8 한국어가 손상되는 것을 방지
    _queries = json.loads(sys.stdin.buffer.read())
    _output  = []

    for item in _queries:
        q      = item["query"]
        top_k  = item.get("top_k", _top_k)
        vec    = _embedder.embed_query(q)
        hits   = hybrid_search(
            query_vec=vec,
            query_text=q,
            metadata=_metadata,
            vector_store=_vector_store,
            top_k=top_k,
            alpha=cfg["search"].get("alpha", 0.7),
        )
        _output.append({
            "query": q,
            "results": [
                {
                    "chunk_id":    r.chunk_id,
                    "score":       round(r.score, 6),
                    "file_path":   r.file_path,
                    "symbol_name": r.symbol_name,
                    "symbol_type": r.symbol_type,
                    "start_line":  r.start_line,
                    "end_line":    r.end_line,
                    "content":     r.content[:constants.PERFORMANCE_THRESHOLDS["content_preview_max_chars"]],
                }
                for r in hits
            ],
        })

    sys.stdout.buffer.write(json.dumps(_output, ensure_ascii=False).encode('utf-8'))
    sys.stdout.buffer.write(b'\n')
    _metadata.close()
    _cache.close()
    _vector_store.close()
    sys.exit(0)