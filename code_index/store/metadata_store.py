import sqlite3
import sys
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
    project_name: str = ""


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
                file_path    TEXT PRIMARY KEY,
                sha256       TEXT NOT NULL,
                mtime        REAL NOT NULL,
                indexed_at   TEXT NOT NULL,
                project_name TEXT NOT NULL DEFAULT ''
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
                content_hash TEXT NOT NULL,
                project_name TEXT NOT NULL DEFAULT ''
            )
        """)
        c.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
            USING fts5(chunk_id UNINDEXED, content, symbol_name, file_path UNINDEXED, project_name UNINDEXED)
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

    def upsert_file(self, file_path: str, sha256: str, mtime: float, project_name: str = ""):
        from datetime import datetime, timezone
        indexed_at = datetime.now(timezone.utc).isoformat()
        self._con.execute(
            "INSERT OR REPLACE INTO files VALUES (?,?,?,?,?)",
            (file_path, sha256, mtime, indexed_at, project_name),
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

    def _delete_files_batch(self, file_paths: list[str]):
        """대량 파일 삭제를 배치로 최적화하여 처리."""
        if not file_paths:
            return
            
        # SQLite IN 절의 제한을 고려하여 배치 크기 설정 (일반적으로 999개까지 지원)
        BATCH_SIZE = 900
        total_batches = (len(file_paths) + BATCH_SIZE - 1) // BATCH_SIZE
        
        for batch_idx in range(total_batches):
            start_idx = batch_idx * BATCH_SIZE
            end_idx = min(start_idx + BATCH_SIZE, len(file_paths))
            batch_paths = file_paths[start_idx:end_idx]
            
            # IN 절용 플레이스홀더 생성
            placeholders = ','.join('?' * len(batch_paths))
            
            # 배치 삭제 실행
            self._con.execute(f"DELETE FROM files WHERE file_path IN ({placeholders})", batch_paths)
            self._con.execute(f"DELETE FROM chunks WHERE file_path IN ({placeholders})", batch_paths)
            self._con.execute(f"DELETE FROM chunks_fts WHERE file_path IN ({placeholders})", batch_paths)
            
            # 진행상황 표시 (큰 배치의 경우)
            if total_batches > 1:
                processed = end_idx
                print(f"[MetadataStore] 배치 삭제 진행: {processed}/{len(file_paths)} 파일", file=sys.stderr)
        
        # 모든 배치 완료 후 한 번만 커밋
        self._con.commit()

    def all_file_paths(self) -> list:
        return [r[0] for r in self._con.execute("SELECT file_path FROM files")]

    def get_project_file_paths(self, project_name: str) -> list:
        """특정 프로젝트의 모든 파일 경로를 반환 (files 테이블 기반).
        
        개선사항:
        - files 테이블의 project_name으로 프로젝트별 파일 직접 조회
        - chunks와 동기화된 정확한 파일 목록 제공
        """
        return [
            r[0] for r in self._con.execute(
                "SELECT file_path FROM files WHERE project_name = ?",
                (project_name,)
            )
        ]

    def delete_project(self, project_name: str) -> dict:
        """특정 프로젝트의 모든 데이터를 삭제하고 삭제된 통계를 반환."""
        # 삭제 전 통계 수집
        project_files = self.get_project_file_paths(project_name)
        chunk_ids = []
        for fpath in project_files:
            chunk_ids.extend(self.get_chunk_ids_for_file(fpath))
        
        # 청크 삭제
        deleted_chunks = len(chunk_ids)
        if chunk_ids:
            placeholders = ','.join('?' * len(chunk_ids))
            self._con.execute(f"DELETE FROM chunks WHERE chunk_id IN ({placeholders})", chunk_ids)
            self._con.execute(f"DELETE FROM chunks_fts WHERE chunk_id IN ({placeholders})", chunk_ids)
        
        # 해당 프로젝트에만 속한 파일들 삭제 (다른 프로젝트에서 참조되지 않는 파일)
        deleted_files = 0
        for fpath in project_files:
            # 이 파일이 다른 프로젝트에서도 사용되는지 확인
            other_chunks = self._con.execute(
                "SELECT COUNT(*) FROM chunks WHERE file_path = ? AND project_name != ?",
                (fpath, project_name)
            ).fetchone()[0]
            
            if other_chunks == 0:
                # 다른 프로젝트에서 사용되지 않으므로 파일 메타데이터도 삭제
                self._con.execute("DELETE FROM files WHERE file_path = ?", (fpath,))
                deleted_files += 1
        
        self._con.commit()
        
        return {
            "project_name": project_name,
            "deleted_files": deleted_files,
            "deleted_chunks": deleted_chunks,
            "chunk_ids": chunk_ids  # 벡터 스토어 삭제용
        }

    # ── 청크 ───────────────────────────────────────────────────────────

    def upsert_chunks(self, chunks: list):
        for c in chunks:
            self._con.execute(
                "INSERT OR REPLACE INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (c.chunk_id, c.file_path, c.language, c.start_line, c.end_line,
                 c.symbol_type, c.symbol_name, c.parent_class, c.namespace,
                 c.content, c.content_hash, c.project_name),
            )
            self._con.execute(
                "INSERT OR REPLACE INTO chunks_fts(chunk_id,content,symbol_name,file_path,project_name) VALUES(?,?,?,?,?)",
                (c.chunk_id, c.content, c.symbol_name, c.file_path, c.project_name),
            )
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
            "SELECT symbol_type, symbol_name, start_line, namespace FROM chunks WHERE file_path=? ORDER BY start_line",
            (file_path,),
        ).fetchall()
        return [{"type": r[0], "name": r[1], "line": r[2], "namespace": r[3]} for r in rows]

    # ── BM25 FTS 검색 ──────────────────────────────────────────────────

    def bm25_search(self, query: str, top_k: int = 20, filters: Optional[dict] = None) -> list:
        """FTS5 BM25 검색. (chunk_id, bm25_score) 리스트 반환."""
        if filters:
            # 필터가 있는 경우 WHERE 조건 추가
            filter_conditions = []
            filter_params = [query]
            
            if "project_name" in filters:
                filter_conditions.append("project_name = ?")
                filter_params.append(filters["project_name"])
                
            if "language" in filters:
                filter_conditions.append("chunks.language = ?")
                filter_params.append(filters["language"])
                
            # FTS와 chunks 테이블 조인하여 필터 적용
            where_clause = " AND " + " AND ".join(filter_conditions) if filter_conditions else ""
            sql = f"""
                SELECT chunks_fts.chunk_id, bm25(chunks_fts) 
                FROM chunks_fts 
                JOIN chunks ON chunks_fts.chunk_id = chunks.chunk_id
                WHERE chunks_fts MATCH ?{where_clause}
                ORDER BY bm25(chunks_fts) 
                LIMIT ?
            """
            filter_params.append(top_k)
            rows = self._con.execute(sql, filter_params).fetchall()
        else:
            # 필터가 없는 경우 기존 방식
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
