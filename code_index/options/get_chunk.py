"""Get chunk functionality."""

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


def get_chunk(cfg):
    """Get chunk details from metadata and output as JSON."""
    
    _chunk_id = _get_arg("--get-chunk")
    if not _chunk_id:
        print("[Error] --get-chunk 다음에 청크 ID(UUID)를 입력하세요.", file=sys.stderr)
        sys.exit(1)

    vs_cfg   = cfg["vector_store"]
    data_dir = vs_cfg.get("data_path", constants.DEFAULT_PATHS["data_dir"])
    meta_path = os.path.join(os.path.dirname(data_dir), constants.DEFAULT_PATHS["metadata_db"])

    _metadata = MetadataStore(meta_path)
    _chunk    = _metadata.get_chunk(_chunk_id)
    _metadata.close()

    if not _chunk:
        print(f"[Error] 존재하지 않는 청크 입니다: {_chunk_id}", file=sys.stderr)
        sys.exit(0)

    _out = {
        "chunk_id":    _chunk.chunk_id,
        "file_path":   _chunk.file_path,
        "language":    _chunk.language,
        "start_line":  _chunk.start_line,
        "end_line":    _chunk.end_line,
        "symbol_type": _chunk.symbol_type,
        "symbol_name": _chunk.symbol_name,
        "parent_class":_chunk.parent_class,
        "namespace":   _chunk.namespace,
        "content":     _chunk.content,
    }
    sys.stdout.buffer.write(json.dumps(_out, ensure_ascii=False, indent=2).encode("utf-8"))
    sys.stdout.buffer.write(b"\n")
    sys.exit(0)