"""
CodeIndex 전역 상수 및 설정값 모음
"""

# ── 시스템 요구사항 ─────────────────────────────────────────────────────────
MIN_PYTHON_VERSION = (3, 10)

# ── CLI 옵션 ────────────────────────────────────────────────────────────────
CLI_FLAGS = {
    "--index-only", "--query-batch", "--help", "--status", "--remove",
    "--search-code", "--get-file-outline", "--get-chunk", "--http-port",
    "--top-k", "--language", "--symbol-type", "--project",
}

# ── 의존성 패키지 ───────────────────────────────────────────────────────────
REQUIRED_PACKAGES = [
    "torch",
    "transformers", 
    "sentencepiece",
    "einops",
    "qdrant_client",
    "grpc",
    "tree_sitter",
    "tree_sitter_cpp",
    "tree_sitter_c_sharp",
    "mcp",
]

PACKAGE_INSTALL_NAMES = {
    "tree_sitter": "tree-sitter>=0.22",
    "tree_sitter_cpp": "tree-sitter-cpp",
    "tree_sitter_c_sharp": "tree-sitter-c-sharp",
    "mcp": "mcp",
    "qdrant_client": "qdrant-client",
    "grpc": "grpcio",
}

TORCH_PACKAGES = ["torch", "torchvision", "torchaudio"]

# ── PyTorch CUDA 설치 URL ───────────────────────────────────────────────────
PYTORCH_CUDA_URLS = {
    "cu128": "https://download.pytorch.org/whl/cu128",
    "cu118": "https://download.pytorch.org/whl/cu118",
}

# ── 기본 경로 ───────────────────────────────────────────────────────────────
DEFAULT_PATHS = {
    "settings": "config/settings.json",
    "data_dir": "./data",
    "metadata_db": "metadata.db",
    "embed_cache_db": "embed_cache.db",
    "cache_dir": ".cache",
    "log_file": "log.txt",
}

# ── 벡터 스토어 ─────────────────────────────────────────────────────────────
VECTOR_STORE_COLLECTION = "code_index_chunks"

# ── 네트워크 포트 ───────────────────────────────────────────────────────────
DEFAULT_PORTS = {
    "qdrant": 6333,
    "mcp_http": 6380,
}

# ── 성능 임계값 ─────────────────────────────────────────────────────────────
PERFORMANCE_THRESHOLDS = {
    "max_vector_count_for_size_check": 1000,
    "max_disk_usage_mb": 100,
    "max_wal_size_mb": 50,
    "content_preview_max_chars": 1000,
}

# ── CUDA 관련 설정 ──────────────────────────────────────────────────────────
CUDA_CONFIG = {
    "min_major_version": 11,
    "min_minor_version": 8,
    "preferred_version": 12,
}
