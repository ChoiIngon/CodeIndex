import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ChunkMeta:
    chunk_id: str
    file_path: str
    language: str
    start_line: int
    end_line: int
    symbol_type: str
    symbol_name: str
    parent_class: str
    namespace: str
    content: str
    content_hash: str


@dataclass
class FileMeta:
    file_path: str
    sha256: str
    mtime: float
    chunk_ids: list = field(default_factory=list)


class MetadataStore:
    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(db_path, check_same_thread=False)
        self._con.execute("PRAGMA journal_mode=WAL")
        self._con.execute("PRAGMA synchronous=NORMAL")
        self._init_tables()

    def _init_tables(self):
        c = self._con
        c.execute("""
            CREATE TABLE IF NOT EXISTS files (
                file_path TEXT PRIMARY KEY,
                sha256    TEXT NOT NULL,
                mtime     REAL NOT NULL,
                indexed_at TEXT NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id     TEXT PRIMARY KEY,
                file_path    TEXT NOT NULL,
                language     TEXT NOT NULL,
                start_line   INTEGER NOT NULL,
                end_line     INTEGER NOT NULL,
                symbol_type  TEXT NOT NULL,
                symbol_name  TEXT NOT NULL,
                parent_class TEXT NOT NULL,
                namespace    TEXT NOT NULL,
                content      TEXT NOT NULL,
                content_hash TEXT NOT NULL
            )
        """)
        c.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
            USING fts5(chunk_id UNINDEXED, content, symbol_name, file_path UNINDEXED)
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_chunks_file ON chunks(file_path)")
        c.commit()

    # ── 파일 상태 ──────────────────────────────────────────────────────

    def get_file(self, file_path: str) -> Optional[FileMeta]:
        row = self._con.execute(
            "SELECT sha256, mtime FROM files WHERE file_path=?", (file_path,)
        ).fetchone()
        if not row:
            return None
        sha256, mtime = row
        chunk_ids = [
            r[0] for r in self._con.execute(
                "SELECT chunk_id FROM chunks WHERE file_path=?", (file_path,)
            )
        ]
        return FileMeta(file_path=file_path, sha256=sha256, mtime=mtime, chunk_ids=chunk_ids)

    def upsert_file(self, file_path: str, sha256: str, mtime: float):
        from datetime import datetime, timezone
        indexed_at = datetime.now(timezone.utc).isoformat()
        self._con.execute(
            "INSERT OR REPLACE INTO files VALUES (?,?,?,?)",
            (file_path, sha256, mtime, indexed_at),
        )
        self._con.commit()

    def get_chunk_ids_for_file(self, file_path: str) -> list:
        return [
            r[0] for r in self._con.execute(
                "SELECT chunk_id FROM chunks WHERE file_path=?", (file_path,)
            )
        ]

    def delete_file(self, file_path: str):
        self._con.execute("DELETE FROM files WHERE file_path=?", (file_path,))
        self._con.execute("DELETE FROM chunks WHERE file_path=?", (file_path,))
        self._con.execute("DELETE FROM chunks_fts WHERE file_path=?", (file_path,))
        self._con.commit()

    def all_file_paths(self) -> list:
        return [r[0] for r in self._con.execute("SELECT file_path FROM files")]

    # ── 청크 ───────────────────────────────────────────────────────────

    def upsert_chunks(self, chunks: list):
        for c in chunks:
            self._con.execute(
                "INSERT OR REPLACE INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (c.chunk_id, c.file_path, c.language, c.start_line, c.end_line,
                 c.symbol_type, c.symbol_name, c.parent_class, c.namespace,
                 c.content, c.content_hash),
            )
            self._con.execute(
                "INSERT OR REPLACE INTO chunks_fts(chunk_id,content,symbol_name,file_path) VALUES(?,?,?,?)",
                (c.chunk_id, c.content, c.symbol_name, c.file_path),
            )
        self._con.commit()

    def delete_chunks(self, chunk_ids: list):
        for cid in chunk_ids:
            self._con.execute("DELETE FROM chunks WHERE chunk_id=?", (cid,))
            self._con.execute("DELETE FROM chunks_fts WHERE chunk_id=?", (cid,))
        self._con.commit()

    def get_chunk(self, chunk_id: str) -> Optional[ChunkMeta]:
        row = self._con.execute(
            "SELECT * FROM chunks WHERE chunk_id=?", (chunk_id,)
        ).fetchone()
        if not row:
            return None
        return ChunkMeta(*row)

    def get_chunks_by_ids(self, chunk_ids: list) -> list:
        result = []
        for cid in chunk_ids:
            c = self.get_chunk(cid)
            if c:
                result.append(c)
        return result

    def get_file_symbols(self, file_path: str) -> list:
        rows = self._con.execute(
            "SELECT symbol_type, symbol_name, start_line FROM chunks WHERE file_path=? ORDER BY start_line",
            (file_path,),
        ).fetchall()
        return [{"type": r[0], "name": r[1], "line": r[2]} for r in rows]

    # ── BM25 FTS 검색 ──────────────────────────────────────────────────

    def bm25_search(self, query: str, top_k: int = 20) -> list:
        """FTS5 BM25 검색. (chunk_id, bm25_score) 리스트 반환."""
        rows = self._con.execute(
            "SELECT chunk_id, bm25(chunks_fts) FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY bm25(chunks_fts) LIMIT ?",
            (query, top_k),
        ).fetchall()
        return [(r[0], -r[1]) for r in rows]  # bm25() 반환값은 음수이므로 부호 반전

    # ── 통계 ───────────────────────────────────────────────────────────

    def stats(self) -> dict:
        n_files = self._con.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        n_chunks = self._con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        return {"total_files": n_files, "total_chunks": n_chunks}

    def project_stats(self, source_paths: list) -> list:
        """source_paths 별로 파일 수, 청크 수, 최종 인덱싱 시각을 반환."""
        result = []
        for sp in source_paths:
            prefix = sp.replace("\\", "/").rstrip("/")
            # LIKE 매칭: 경로 구분자를 통일한 뒤 비교
            rows = self._con.execute(
                "SELECT file_path, indexed_at FROM files"
            ).fetchall()
            matched = [
                (fp, ia) for fp, ia in rows
                if fp.replace("\\", "/").startswith(prefix)
            ]
            n_files = len(matched)
            last_indexed = max((ia for _, ia in matched), default=None) if matched else None
            # 청크 수
            n_chunks = 0
            for fp, _ in matched:
                n_chunks += self._con.execute(
                    "SELECT COUNT(*) FROM chunks WHERE file_path=?", (fp,)
                ).fetchone()[0]
            result.append({
                "source_path": sp,
                "files": n_files,
                "chunks": n_chunks,
                "last_indexed": last_indexed,
            })
        return result

    def close(self):
        self._con.close()
