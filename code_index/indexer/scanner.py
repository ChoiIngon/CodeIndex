import fnmatch
import hashlib
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Generator


@dataclass
class FileChange:
    path: str
    status: str  # "new" | "modified" | "deleted"


def scan_files(source_paths: list, extensions: list, exclude_patterns: list) -> Generator[str, None, None]:
    """소스 경로에서 대상 확장자 파일을 순회."""
    ext_set = {e.lower() for e in extensions}
    for src in source_paths:
        for root, dirs, files in os.walk(src):
            root_path = Path(root)
            dirs[:] = [
                d for d in dirs
                if not _is_excluded(str(root_path / d), exclude_patterns)
            ]
            for fname in files:
                if Path(fname).suffix.lower() in ext_set:
                    full = str(root_path / fname)
                    if not _is_excluded(full, exclude_patterns):
                        yield full


def _is_excluded(path: str, patterns: list) -> bool:
    normalized = path.replace("\\", "/")
    for pat in patterns:
        if fnmatch.fnmatch(normalized, pat):
            return True
    return False


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def detect_changes(current_files: list, metadata_store, source_paths: list = None, project_name: str = None) -> tuple[list, list, list]:
    """
    (new_files, modified_files, deleted_files) 반환.
    mtime 선행 체크 → 변경 시 SHA256 재계산.
    project_name과 source_paths를 사용하여 프로젝트별 독립적인 변경 감지 수행.
    """
    current_set = set(current_files)
    
    # 프로젝트별 독립 처리
    if project_name and source_paths:
        # 1. 해당 프로젝트의 모든 기존 파일 가져오기
        all_project_files = metadata_store.get_project_file_paths(project_name)
        
        # 2. 현재 source_paths 범위 내/외로 분류
        indexed_files_in_scope = []
        indexed_files_out_of_scope = []
        
        for indexed_file in all_project_files:
            normalized_indexed = indexed_file.replace("\\", "/")
            is_in_current_scope = False
            
            for source_path in source_paths:
                normalized_source = source_path.replace("\\", "/").rstrip("/")
                
                # 정확한 경로 매칭: 파일이 현재 source_path 범위에 있는지 확인
                if (normalized_indexed == normalized_source or 
                    normalized_indexed.startswith(normalized_source + "/")):
                    indexed_files_in_scope.append(indexed_file)
                    is_in_current_scope = True
                    break
            
            if not is_in_current_scope:
                indexed_files_out_of_scope.append(indexed_file)
        
        # 3. 범위 내 파일들과 현재 파일들 비교 + 범위 외 파일들은 모두 삭제
        indexed_set = set(indexed_files_in_scope)
        deleted_from_scope = [f for f in indexed_set if f not in current_set]
        deleted_out_of_scope = indexed_files_out_of_scope
        
        new_files = [f for f in current_set if f not in indexed_set]
        deleted_files = deleted_from_scope + deleted_out_of_scope
        modified_files = []
        
        # 변경 감지할 파일들 (범위 내의 기존 파일과 현재 파일의 교집합)
        files_to_check = list(current_set & indexed_set)
        
    elif source_paths:
        # 기존 경로 기반 로직 (하위 호환성)
        all_indexed_files = metadata_store.all_file_paths()
        indexed_files = []
        for indexed_file in all_indexed_files:
            normalized_indexed = indexed_file.replace("\\", "/")
            for source_path in source_paths:
                normalized_source = source_path.replace("\\", "/").rstrip("/")
                
                if (normalized_indexed == normalized_source or 
                    normalized_indexed.startswith(normalized_source + "/")):
                    indexed_files.append(indexed_file)
                    break
        indexed_set = set(indexed_files)
        new_files = [f for f in current_set if f not in indexed_set]
        deleted_files = [f for f in indexed_set if f not in current_set]
        modified_files = []
        files_to_check = list(current_set & indexed_set)
        
    else:
        indexed_set = set(metadata_store.all_file_paths())
        new_files = [f for f in current_set if f not in indexed_set]
        deleted_files = [f for f in indexed_set if f not in current_set]
        modified_files = []
        files_to_check = list(current_set & indexed_set)

    # 변경 감지 (mtime → SHA256 체크)
    if files_to_check:
        print(f"[변경감지] {len(files_to_check)}개 파일 변경 감지 시작...", file=sys.stderr)
        
        start_time = time.time()
        last_update_time = 0
        
        for i, fpath in enumerate(files_to_check):
            try:
                mtime = os.path.getmtime(fpath)
            except OSError:
                continue
                
            meta = metadata_store.get_file(fpath)
            if not meta:
                new_files.append(fpath)
                continue
                
            # mtime 체크 먼저
            if abs(mtime - meta.mtime) < 0.01:
                continue  # mtime 동일 → 변경 없음
            
            # SHA256 체크 (시간이 오래 걸림)
            now = time.time()
            if now - last_update_time >= 1.0 or i == len(files_to_check) - 1:
                elapsed = now - start_time
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                pct = ((i + 1) * 100) // len(files_to_check)
                
                remaining = (len(files_to_check) - i - 1) / rate if rate > 0 else 0
                eta_str = f" - 약 {remaining:.0f}초 남음" if remaining > 2 else ""
                
                print(
                    f"\r[변경감지] {i+1}/{len(files_to_check)}개 ({pct}%) - "
                    f"{rate:.1f}파일/s{eta_str}",
                    end="", file=sys.stderr, flush=True
                )
                last_update_time = now
            
            if file_sha256(fpath) != meta.sha256:
                modified_files.append(fpath)
        
        # 완료 메시지
        elapsed = time.time() - start_time
        rate = len(files_to_check) / elapsed if elapsed > 0 else 0
        print(
            f"\r[변경감지] 완료 ({len(files_to_check)}개, {elapsed:.1f}s, {rate:.1f}파일/s) - "
            f"수정={len(modified_files)}개 발견",
            file=sys.stderr
        )

    return new_files, modified_files, deleted_files
