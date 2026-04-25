import sqlite3
import struct
from pathlib import Path
from typing import Optional, Set


class EmbedCache:
    """content_hash → 임베딩 벡터 SQLite 캐시"""

    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(db_path, check_same_thread=False)
        self._con.execute("PRAGMA journal_mode=WAL")
        self._con.execute("""
            CREATE TABLE IF NOT EXISTS embeddings (
                content_hash TEXT PRIMARY KEY,
                vector       BLOB NOT NULL
            )
        """)
        self._con.commit()

    def get(self, content_hash: str) -> Optional[list]:
        row = self._con.execute(
            "SELECT vector FROM embeddings WHERE content_hash=?", (content_hash,)
        ).fetchone()
        if not row:
            return None
        n = len(row[0]) // 4
        return list(struct.unpack(f"{n}f", row[0]))

    def set(self, content_hash: str, vector: list):
        blob = struct.pack(f"{len(vector)}f", *vector)
        self._con.execute(
            "INSERT OR REPLACE INTO embeddings VALUES (?,?)", (content_hash, blob)
        )
        self._con.commit()

    def delete_unused_hashes(self, used_hashes: Set[str]):
        """사용되지 않는 content_hash들의 임베딩 캐시를 삭제."""
        if not used_hashes:
            # 모든 캐시 삭제
            self._con.execute("DELETE FROM embeddings")
        else:
            # 사용되지 않는 해시들만 삭제 (NOT IN 사용)
            placeholders = ",".join(["?"] * len(used_hashes))
            self._con.execute(
                f"DELETE FROM embeddings WHERE content_hash NOT IN ({placeholders})",
                list(used_hashes)
            )
        self._con.commit()

    def get_stats(self) -> dict:
        """캐시 통계 반환."""
        row = self._con.execute("SELECT COUNT(*), SUM(LENGTH(vector)) FROM embeddings").fetchone()
        count, total_bytes = row
        return {
            "cached_embeddings": count or 0,
            "cache_size_mb": round((total_bytes or 0) / (1024 * 1024), 1)
        }

    def close(self):
        self._con.close()
