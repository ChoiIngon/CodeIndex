import sqlite3
import struct
from pathlib import Path
from typing import Optional


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

    def close(self):
        self._con.close()
