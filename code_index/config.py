import json
import sys
from pathlib import Path

_DEFAULT = {
    "indexer": {
		# 프로젝트별 설정
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
        "data_dir": "./data",
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


def get_all_projects(config: dict) -> dict:
    """프로젝트별 설정을 반환."""
    indexer_cfg = config.get("indexer", {})
    
    # chunk 관련 설정은 제외하고 프로젝트 설정만 반환
    projects = {}
    for key, value in indexer_cfg.items():
        if key not in ["chunk_min_lines", "chunk_max_lines", "chunk_overlap_lines", "chunk_workers"]:
            projects[key] = value
    
    return projects


def get_all_source_paths(config: dict) -> list[str]:
    """모든 프로젝트의 source_paths를 합친 리스트 반환."""
    projects = get_all_projects(config)
    all_paths = []
    for project_name, project_config in projects.items():
        all_paths.extend(project_config.get("source_paths", []))
    return all_paths


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
    else:
        # settings.json이 존재하지 않는 경우 에러 메시지 출력
        template_path = Path(__file__).parent.parent / "config" / "settings.json.template"

        print("=" * 70)
        print("CodeIndex 설정 파일이 없습니다!")
        print("=" * 70)
            
        if template_path.exists():
            print(f"\n다음 단계를 따라 설정을 완료하세요:")
            print(f"1. 템플릿 파일을 복사하세요:")
            print(f"   copy \"{template_path}\" \"{template_path.parent / 'settings.json'}\"")
            print(f"\n2. settings.json 파일에서 'indexer' 섹션의 프로젝트 설정을 수정하세요:")
            print(f"   - 'source_paths'를 실제 프로젝트 경로로 변경")
            print(f"   - 필요없는 프로젝트 섹션 삭제")
            print(f"   - 'extensions'와 'exclude_patterns' 필요시 조정")
            print(f"\n3. MCP 서버를 다시 시작하세요")
            print("=" * 70)
        else:
            print(f"\n설정 파일을 생성하세요:")
            print(f"파일: {Path(__file__).parent.parent / 'config' / 'settings.json'}")
            print(f"\n최소 설정 예시:")
            print(f'{{\n  "indexer": {{\n    "MyProject": {{\n      "source_paths": ["/path/to/your/source"],\n      "extensions": [".cpp", ".h", ".cs"],\n      "exclude_patterns": []\n    }}\n  }}\n}}')
            print("=" * 70)
        sys.exit(1)

    return settings
