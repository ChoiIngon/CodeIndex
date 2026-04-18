from __future__ import annotations

import os
import sys
from typing import Optional

from ..config import load_config
from ..indexer.embedder import Embedder
from ..models.model_manager import resolve_model
from ..retriever.hybrid_search import SearchResult, hybrid_search
from ..store.cache import EmbedCache
from ..store.metadata_store import MetadataStore
from ..store.vector_store import VectorStore
from .debug_logger import DebugLogger


def start_server(cfg: Optional[dict] = None, http_port: Optional[int] = None) -> None:
    if cfg is None:
        cfg = load_config()

    from mcp.server.fastmcp import FastMCP

    emb_cfg = cfg["embedding"]
    vs_cfg = cfg["vector_store"]
    model_cfg = cfg["models"]
    search_cfg = cfg["search"]

    data_dir = vs_cfg.get("data_path", "./data/qdrant")
    meta_path = os.path.join(os.path.dirname(data_dir), "metadata.db")
    cache_path = os.path.join(os.path.dirname(data_dir), "embed_cache.db")

    metadata = MetadataStore(meta_path)
    cache = EmbedCache(cache_path)
    vector_store = VectorStore(vs_cfg, emb_cfg["vector_size"])

    embed_model_path = resolve_model(model_cfg["embed"], model_cfg.get("cache_dir", ""))
    embedder = Embedder(embed_model_path, emb_cfg, cache)

    reranker = None
    if search_cfg.get("use_reranker", False):
        from ..retriever.reranker import Reranker
        rerank_path = resolve_model(model_cfg["rerank"], model_cfg.get("cache_dir", ""))
        reranker = Reranker(rerank_path, emb_cfg)

    _debug = cfg.get("debug", False)
    _logger = DebugLogger("log.txt", echo_stderr=(http_port is not None and _debug)) if _debug else None

    if http_port is not None:
        host = "127.0.0.1"
        mcp_instance = FastMCP("MapleCodeIndex", host=host, port=http_port)
    else:
        mcp_instance = FastMCP("MapleCodeIndex")

    mcp = mcp_instance

    @mcp.tool()
    def search_code(
        query: str,
        top_k: int = search_cfg.get("top_k", 20),
        language: str = "",
        symbol_type: str = "",
    ) -> list[dict]:
        """코드베이스를 자연어 또는 심볼명으로 검색합니다.

        Args:
            query: 검색할 자연어 쿼리 또는 심볼명
            top_k: 반환할 최대 결과 수 (기본값 20)
            language: 필터할 언어 (예: cpp, cs, 빈 문자열이면 전체)
            symbol_type: 필터할 심볼 타입 (예: function, class, method)
        """
        if _logger:
            _logger.log_input("search_code", {"query": query, "top_k": top_k, "language": language, "symbol_type": symbol_type})

        query_vec = embedder.embed_query(query)
        filters: dict = {}
        if language:
            filters["language"] = language
        if symbol_type:
            filters["symbol_type"] = symbol_type

        results = hybrid_search(
            query_vec=query_vec,
            query_text=query,
            metadata=metadata,
            vector_store=vector_store,
            top_k=top_k,
            alpha=search_cfg.get("alpha", 0.7),
            filters=filters or None,
        )

        rerank_k = search_cfg.get("rerank_top_k", 8)
        if reranker and results:
            results = reranker.rerank(query, results, top_k=rerank_k)

        output = [_result_to_dict(r) for r in results]
        if _logger:
            _logger.log_output("search_code", output)
        return output

    @mcp.tool()
    def get_file_outline(file_path: str) -> list[dict]:
        """파일의 심볼 목록(클래스/함수/메서드)을 반환합니다.

        Args:
            file_path: 아웃라인을 가져올 파일의 절대 경로 또는 상대 경로
        """
        if _logger:
            _logger.log_input("get_file_outline", {"file_path": file_path})

        symbols = metadata.get_file_symbols(file_path)
        if not symbols:
            # 경로 일부 매칭 시도
            all_paths = metadata.all_file_paths()
            matches = [p for p in all_paths if file_path.replace("\\", "/") in p.replace("\\", "/")]
            if matches:
                symbols = metadata.get_file_symbols(matches[0])

        if _logger:
            _logger.log_output("get_file_outline", symbols)
        return symbols

    @mcp.tool()
    def get_chunk(chunk_id: str) -> Optional[dict]:
        """청크 ID로 특정 코드 청크를 조회합니다.

        Args:
            chunk_id: 조회할 청크의 UUID
        """
        if _logger:
            _logger.log_input("get_chunk", {"chunk_id": chunk_id})

        chunk = metadata.get_chunk(chunk_id)
        if not chunk:
            if _logger:
                _logger.log_output("get_chunk", None)
            return None

        output = {
            "chunk_id": chunk.chunk_id,
            "file_path": chunk.file_path,
            "language": chunk.language,
            "start_line": chunk.start_line,
            "end_line": chunk.end_line,
            "symbol_type": chunk.symbol_type,
            "symbol_name": chunk.symbol_name,
            "parent_class": chunk.parent_class,
            "namespace": chunk.namespace,
            "content": chunk.content,
        }
        if _logger:
            _logger.log_output("get_chunk", output)
        return output

    if http_port is not None:
        print(f"[MCP] MapleCodeIndex MCP 서버 시작 (HTTP  http://127.0.0.1:{http_port}/mcp)...", file=sys.stderr)
        mcp.run(transport="streamable-http")
    else:
        print("[MCP] MapleCodeIndex MCP 서버 시작 (stdio)...", file=sys.stderr)
        mcp.run(transport="stdio")


def _result_to_dict(r: SearchResult) -> dict:
    return {
        "chunk_id": r.chunk_id,
        "score": round(r.score, 6),
        "file_path": r.file_path,
        "language": r.language,
        "start_line": r.start_line,
        "end_line": r.end_line,
        "symbol_type": r.symbol_type,
        "symbol_name": r.symbol_name,
        "parent_class": r.parent_class,
        "namespace": r.namespace,
        "content": r.content,
    }
