from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    HnswConfigDiff,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
    Filter,
    FieldCondition,
    MatchValue,
    ScoredPoint,
)


@dataclass
class SearchResult:
    chunk_id: str
    score: float
    file_path: str
    language: str
    symbol_type: str
    symbol_name: str
    start_line: int
    end_line: int


class VectorStore:
    COLLECTION = "code_index_chunks"

    def __init__(self, vs_cfg: dict, vector_size: int):
        self._vector_size = vector_size
        self._collection = vs_cfg.get("collection", self.COLLECTION)

        mode = vs_cfg.get("mode", "server")
        if mode == "server":
            host      = vs_cfg.get("host", "localhost")
            port      = int(vs_cfg.get("port", 6333))
            grpc_port = int(vs_cfg.get("grpc_port", port + 1))
            
            # gRPC 우선 시도 후 실패 시 HTTP로 폴백
            self._client = self._create_client_with_fallback(host, port, grpc_port)
        else:
            data_path = vs_cfg.get("data_path", "./data/qdrant")
            Path(data_path).mkdir(parents=True, exist_ok=True)
            self._client = QdrantClient(path=data_path)

        self._ensure_collection()

    def close(self):
        self._client.close()

    def _create_client_with_fallback(self, host: str, port: int, grpc_port: int) -> QdrantClient:
        """gRPC 우선 시도 후 연결 실패 시 HTTP로 폴백하는 클라이언트 생성"""
        import socket

        # 1단계: TCP 소켓으로 gRPC 포트 실제 개방 여부 먼저 확인
        grpc_available = False
        try:
            with socket.create_connection((host, grpc_port), timeout=1):
                grpc_available = True
        except (socket.error, socket.timeout, OSError):
            pass

        if grpc_available:
            try:
                print(f"[벡터DB] gRPC 연결 시도 중... ({host}:{grpc_port})", file=sys.stderr)
                client_grpc = QdrantClient(
                    host=host,
                    port=port,
                    grpc_port=grpc_port,
                    prefer_grpc=True,
                )
                client_grpc.get_collections()
                print(f"[벡터DB] gRPC 연결 성공 → 고성능 모드", file=sys.stderr)
                return client_grpc
            except Exception as grpc_error:
                print(f"[벡터DB] gRPC 연결 실패: {grpc_error}", file=sys.stderr)
        else:
            grpc_error = f"포트 {grpc_port} 닫혀 있음"
            print(f"[벡터DB] gRPC 포트 미개방 ({host}:{grpc_port}) → HTTP 모드로 전환", file=sys.stderr)
            
            # 2단계: HTTP 모드로 폴백
            try:
                print(f"[벡터DB] HTTP 연결 시도 중... ({host}:{port})", file=sys.stderr)
                client_http = QdrantClient(
                    host=host,
                    port=port,
                    grpc_port=grpc_port,
                    prefer_grpc=False,
                )
                
                # HTTP 연결 테스트
                client_http.get_collections()
                print(f"[벡터DB] HTTP 연결 성공 → 안정성 모드", file=sys.stderr)
                return client_http
                
            except Exception as http_error:
                print(f"[벡터DB] HTTP 연결도 실패: {http_error}", file=sys.stderr)
                raise RuntimeError(
                    f"Qdrant 서버에 연결할 수 없습니다. gRPC 오류: {grpc_error}, HTTP 오류: {http_error}"
                )

    def _ensure_collection(self):
        existing = [c.name for c in self._client.get_collections().collections]
        if self._collection in existing:
            return

        print(f"[벡터DB] 컬렉션 생성: {self._collection}", file=sys.stderr)
        self._client.create_collection(
            collection_name=self._collection,
            vectors_config=VectorParams(
                size=self._vector_size,
                distance=Distance.COSINE,
                on_disk=True,
            ),
            hnsw_config=HnswConfigDiff(
                m=16,
                ef_construct=200,
                full_scan_threshold=10,  # server mode 최솟값 10 (항상 HNSW 사용)
            ),
        )
        for field_name, schema in [
            ("file_path", PayloadSchemaType.KEYWORD),
            ("language", PayloadSchemaType.KEYWORD),
            ("symbol_type", PayloadSchemaType.KEYWORD),
            ("parent_class", PayloadSchemaType.KEYWORD),
            ("project_name", PayloadSchemaType.KEYWORD),
        ]:
            self._client.create_payload_index(
                collection_name=self._collection,
                field_name=field_name,
                field_schema=schema,
            )

    def upsert_batch(self, chunks: list, vecs: list):
        """chunks: list[Chunk], vecs: list[list[float]]"""
        if not chunks:
            return
        points = [
            PointStruct(
                id=_id_to_uint64(c.chunk_id),
                vector=vec,
                payload={
                    "chunk_id":    c.chunk_id,
                    "file_path":   c.file_path,
                    "language":    c.language,
                    "start_line":  c.start_line,
                    "end_line":    c.end_line,
                    "symbol_type": c.symbol_type,
                    "symbol_name": c.symbol_name,
                    "parent_class": c.parent_class,
                    "namespace":   c.namespace,
                    "project_name": c.project_name,
                },
            )
            for c, vec in zip(chunks, vecs)
        ]
        self._client.upsert(collection_name=self._collection, points=points)

    def delete(self, chunk_ids: list):
        if not chunk_ids:
            return
            
        # 대량 삭제 시 진행률 표시
        if len(chunk_ids) > 500:
            print(f"[벡터삭제] {len(chunk_ids)}개 청크 삭제 시작...", file=sys.stderr)
            start_time = time.time()
        
        from qdrant_client.models import PointIdsList
        self._client.delete(
            collection_name=self._collection,
            points_selector=PointIdsList(points=[_id_to_uint64(cid) for cid in chunk_ids]),
        )
        
        if len(chunk_ids) > 500:
            elapsed = time.time() - start_time
            rate = len(chunk_ids) / elapsed if elapsed > 0 else 0
            print(f"[벡터삭제] 완료 ({len(chunk_ids)}개, {elapsed:.1f}s, {rate:.0f}청크/s)", file=sys.stderr)

    def search(self, query_vector: list, top_k: int = 20, filter_dict: Optional[dict] = None) -> list[SearchResult]:
        q_filter = _build_filter(filter_dict) if filter_dict else None
        response = self._client.query_points(
            collection_name=self._collection,
            query=query_vector,
            limit=top_k,
            query_filter=q_filter,
            with_payload=True,
        )
        hits: list[ScoredPoint] = response.points
        results = []
        for h in hits:
            p = h.payload or {}
            results.append(SearchResult(
                chunk_id=p.get("chunk_id", ""),
                score=h.score,
                file_path=p.get("file_path", ""),
                language=p.get("language", ""),
                symbol_type=p.get("symbol_type", ""),
                symbol_name=p.get("symbol_name", ""),
                start_line=p.get("start_line", 0),
                end_line=p.get("end_line", 0),
            ))
        return results

    def count(self) -> int:
        """벡터 스토어에 저장된 포인트(청크) 개수 반환."""
        try:
            info = self._client.get_collection(self._collection)
            return info.points_count or 0
        except Exception:
            return 0

def _id_to_uint64(chunk_id: str) -> int:
    import hashlib
    digest = hashlib.md5(chunk_id.encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _build_filter(filter_dict: dict) -> Filter:
    conditions = []
    for key, value in filter_dict.items():
        conditions.append(FieldCondition(key=key, match=MatchValue(value=value)))
    return Filter(must=conditions)
