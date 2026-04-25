"""Get file outline functionality."""

import json
import os
import sys
from pathlib import Path

from code_index import constants
from code_index.config import load_config
from code_index.store.metadata_store import MetadataStore


def _get_arg(flag: str, default=None):
    """sys.argv 에서 'flag VALUE' 형태의 값을 반환."""
    if flag in sys.argv:
        idx = sys.argv.index(flag)
        if idx + 1 < len(sys.argv):
            return sys.argv[idx + 1]
    return default


def get_file_outline(cfg):
    """Get file outline (symbols) from metadata and output as JSON."""
    
    _path = _get_arg("--get-file-outline")
    if not _path:
        print("[Error] --get-file-outline 다음에 파일 경로를 입력하세요.", file=sys.stderr)
        sys.exit(1)

    vs_cfg   = cfg["vector_store"]
    data_dir = vs_cfg.get("data_path", constants.DEFAULT_PATHS["data_dir"])
    meta_path = os.path.join(os.path.dirname(data_dir), constants.DEFAULT_PATHS["metadata_db"])

    _metadata = MetadataStore(meta_path)
    _symbols  = _metadata.get_file_symbols(_path)
    if not _symbols:
        all_paths = _metadata.all_file_paths()
        matches   = [p for p in all_paths if _path.replace("\\", "/") in p.replace("\\", "/")]
        if matches:
            _symbols = _metadata.get_file_symbols(matches[0])
    _metadata.close()

    sys.stdout.buffer.write(json.dumps(_symbols, ensure_ascii=False, indent=2).encode("utf-8"))
    sys.stdout.buffer.write(b"\n")
    sys.exit(0)