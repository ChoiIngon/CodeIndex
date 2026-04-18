import os


def resolve_model(model_ref: str, cache_dir: str = "") -> str:
    """모델 식별자 반환. sentence-transformers가 HuggingFace에서 자동 다운로드·캐싱."""
    if cache_dir:
        os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", cache_dir)
        os.environ.setdefault("HF_HOME", cache_dir)
    return model_ref
