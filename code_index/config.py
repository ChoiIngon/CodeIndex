import json
import sys
from pathlib import Path

_DEFAULT = {
    "indexer": {
        "source_paths": [],
        "extensions": [".cpp", ".h", ".c", ".cs"],
        "exclude_patterns": [
            "*/build/*", "*/.git/*", "*/generated/*",
            "*/Packages/*", "*/Library/*",
        ],
        "chunk_min_lines": 5,
        "chunk_max_lines": 80,
        "chunk_overlap_lines": 10,
    },
    "models": {
        "cache_dir": "",
        "embed": "BAAI/bge-m3",
        "rerank": "cross-encoder/ms-marco-MiniLM-L-12-v2",
    },
    "embedding": {"vector_size": 1024, "batch_size": 64, "n_gpu_layers": -1},
    "vector_store": {
        "mode": "server",
        "host": "localhost",
        "port": 6333,
        "data_path": "./data/qdrant",
        "collection": "code_index_chunks",
    },
    "search": {
        "top_k": 20,
        "rerank_top_k": 8,
        "min_score": 0.0,
        "alpha": 0.5,
        "use_reranker": False,
    },
    "debug": False,
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load_config(path: str = "") -> dict:
    if not path:
        candidates = [
            Path("config/settings.json"),
            Path(__file__).parent.parent / "config" / "settings.json",
        ]
        for c in candidates:
            if c.exists():
                path = str(c)
                break

    settings = dict(_DEFAULT)
    if path and Path(path).exists():
        with open(path, encoding="utf-8-sig") as f:
            raw = f.read()
        try:
            user = json.loads(raw)
        except json.JSONDecodeError as e:
            lines = raw.splitlines()
            bad_line = lines[e.lineno - 1] if e.lineno <= len(lines) else ""
            print(f"설정 데이터 에러 :\n - 경로 : {path}({e.lineno})\n - 원인 : {e.msg}\n - 내용 : {bad_line}")
            sys.exit(1)
        settings = _deep_merge(settings, user)

    return settings
