import fnmatch
import hashlib
import os
from dataclasses import dataclass, field
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


def detect_changes(current_files: list, metadata_store) -> tuple[list, list, list]:
    """
    (new_files, modified_files, deleted_files) 반환.
    mtime 선행 체크 → 변경 시 SHA256 재계산.
    """
    current_set = set(current_files)
    indexed_set = set(metadata_store.all_file_paths())

    new_files = [f for f in current_set if f not in indexed_set]
    deleted_files = [f for f in indexed_set if f not in current_set]
    modified_files = []

    for fpath in current_set & indexed_set:
        try:
            mtime = os.path.getmtime(fpath)
        except OSError:
            continue
        meta = metadata_store.get_file(fpath)
        if not meta:
            new_files.append(fpath)
            continue
        if abs(mtime - meta.mtime) < 0.01:
            continue  # mtime 동일 → 변경 없음
        if file_sha256(fpath) != meta.sha256:
            modified_files.append(fpath)

    return new_files, modified_files, deleted_files
