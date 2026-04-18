from __future__ import annotations

import sys
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
    COLLECTION = "maple_code_chunks"

    def __init__(self, vs_cfg: dict, vector_size: int):
        self._vector_size = vector_size
        self._collection = vs_cfg.get("collection", self.COLLECTION)

        data_path = vs_cfg.get("data_path", "./data/qdrant")
        Path(data_path).mkdir(parents=True, exist_ok=True)
        self._client = QdrantClient(path=data_path)

        self._ensure_collection()

    def close(self):
        self._client.close()

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
                full_scan_threshold=0,  # 항상 HNSW 사용
            ),
        )
        for field_name, schema in [
            ("file_path", PayloadSchemaType.KEYWORD),
            ("language", PayloadSchemaType.KEYWORD),
            ("symbol_type", PayloadSchemaType.KEYWORD),
            ("parent_class", PayloadSchemaType.KEYWORD),
        ]:
            self._client.create_payload_index(
                collection_name=self._collection,
                field_name=field_name,
                field_schema=schema,
            )

    def upsert(self, chunk_id: str, vector: list, payload: dict):
        self._client.upsert(
            collection_name=self._collection,
            points=[PointStruct(id=_id_to_uint64(chunk_id), vector=vector, payload={**payload, "chunk_id": chunk_id})],
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
                },
            )
            for c, vec in zip(chunks, vecs)
        ]
        self._client.upsert(collection_name=self._collection, points=points)

    def delete(self, chunk_ids: list):
        if not chunk_ids:
            return
        from qdrant_client.models import PointIdsList
        self._client.delete(
            collection_name=self._collection,
            points_selector=PointIdsList(points=[_id_to_uint64(cid) for cid in chunk_ids]),
        )

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
        return self._client.count(collection_name=self._collection).count


def _id_to_uint64(chunk_id: str) -> int:
    import hashlib
    digest = hashlib.md5(chunk_id.encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _build_filter(filter_dict: dict) -> Filter:
    conditions = []
    for key, value in filter_dict.items():
        conditions.append(FieldCondition(key=key, match=MatchValue(value=value)))
    return Filter(must=conditions)
