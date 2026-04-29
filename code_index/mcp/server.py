from __future__ import annotations

import os
import sys
from typing import Optional

from code_index.config import load_config
from code_index.indexer.embedder import Embedder
from code_index.models.model_manager import resolve_model
from code_index.retriever.hybrid_search import SearchResult, hybrid_search
from code_index.store.cache import EmbedCache
from code_index.store.metadata_store import MetadataStore
from code_index.store.vector_store import VectorStore
from code_index.mcp.debug_logger import DebugLogger


def start_server(cfg: Optional[dict] = None, http_port: Optional[int] = None) -> None:
    if cfg is None:
        cfg = load_config()

    # Python 3.10 미만에서는 MCP 서버 지원 안함
    if sys.version_info < (3, 10):
        print(f"[Error] MCP 서버는 Python 3.10+ 에서만 지원됩니다. (현재: {sys.version})", file=sys.stderr)
        print("[Error] 다음 옵션을 사용하세요:", file=sys.stderr)
        print("  --index-only     : 인덱싱만 실행", file=sys.stderr)
        print("  --search-code    : 코드 검색", file=sys.stderr)
        print("  --query-batch    : 일괄 검색", file=sys.stderr)
        sys.exit(1)

    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        print("[Error] MCP 패키지가 설치되지 않았습니다. Python 3.10+ 에서 'pip install mcp'로 설치하세요.", file=sys.stderr)
        sys.exit(1)

    emb_cfg = cfg["embedding"]
    vs_cfg = cfg["vector_store"]
    model_cfg = cfg["models"]
    search_cfg = cfg["search"]

    data_dir = vs_cfg.get("data_dir", "./data")
    meta_path = os.path.join(data_dir, "metadata.db")
    cache_path = os.path.join(data_dir, "embed_cache.db")

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
        # FastMCP를 stateless 모드로 설정하여 세션 ID 없이 동작하도록 수정
        mcp_instance = FastMCP(
            name="CodeIndex",
            host=host,
            port=http_port,
            debug=_debug,
            log_level="DEBUG" if _debug else "INFO",
            stateless_http=True,  # AI 클라이언트 호환을 위한 stateless 모드
            json_response=True    # JSON 응답 활성화
        )
    else:
        mcp_instance = FastMCP(
            name="CodeIndex",
            debug=_debug,
            log_level="DEBUG" if _debug else "INFO"
        )

    mcp = mcp_instance

    @mcp.tool()
    def search_code(
        query: str,
        top_k: int = search_cfg.get("top_k", 20),
        language: str = "",
        symbol_type: str = "",
        project: str = "",
    ) -> list[dict]:
        """코드베이스를 자연어 또는 심볼명으로 검색합니다.

        Args:
            query: 검색할 자연어 쿼리 또는 심볼명
            top_k: 반환할 최대 결과 수 (기본값 20)
            language: 필터할 언어 (예: cpp, cs, 빈 문자열이면 전체)
            symbol_type: 필터할 심볼 타입 (예: function, class, method)
            project: 필터할 프로젝트 이름 (예: GameServer, Middleware)
        
        사용 예시:
        - 기본 검색: search_code("패킷 처리")
        - 언어별 검색: search_code("CalculateDamage", language="cpp")
        - 프로젝트별 검색: search_code("QA_Login serialize", project="GameServer")
        - 프로젝트 간 비교: 
          1) search_code("QA_Login serialize", project="GameServer")
          2) search_code("QA_Login deserialize", project="Middleware")
          결과를 비교하여 데이터 타입과 순서 일치 여부 확인
        
        반환값:
        - chunk_id: 청크 고유 ID
        - score: 검색 관련도 점수
        - file_path: 파일 경로
        - symbol_name, symbol_type: 심볼 정보
        - start_line, end_line: 코드 라인 범위
        - content: 코드 내용 (최대 1000자)
        - project_name: 프로젝트 이름
        """
        if _logger:
            _logger.log_input("search_code", {"query": query, "top_k": top_k, "language": language, "symbol_type": symbol_type, "project": project})

        query_vec = embedder.embed_query(query)
        filters: dict = {}
        if language:
            filters["language"] = language
        if symbol_type:
            filters["symbol_type"] = symbol_type
        if project:
            filters["project_name"] = project

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
        print(f"[MCP] CodeIndex MCP 서버 시작 (HTTP  http://127.0.0.1:{http_port}/mcp)...", file=sys.stderr)
        mcp.run(transport="streamable-http")
    else:
        print("[MCP] CodeIndex MCP 서버 시작 (stdio)...", file=sys.stderr)
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
        "project_name": r.project_name,
    }
