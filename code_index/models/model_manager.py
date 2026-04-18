import os
from pathlib import Path

# 프로젝트 루트 기준 .cache (설정에서 cache_dir 미지정 시 사용)
_DEFAULT_CACHE_DIR = str(Path(__file__).parent.parent.parent / ".cache")


def resolve_model(model_ref: str, cache_dir: str = "") -> str:
    """모델 식별자 반환. sentence-transformers가 HuggingFace에서 자동 다운로드·캐싱."""
    resolved = cache_dir.strip() if cache_dir.strip() else _DEFAULT_CACHE_DIR
    os.environ["SENTENCE_TRANSFORMERS_HOME"] = resolved
    os.environ["HF_HOME"] = resolved
    return model_ref
