from __future__ import annotations

# ── 패키지 컨텍스트 보정 ──────────────────────────────────────────────────────
# `python code_index` (디렉토리 직접 실행) 시 __package__ 미설정으로
# 상대 임포트가 실패하는 경우 보정.
if __package__ is None or __package__ == "":
    import sys as _sys
    from pathlib import Path as _Path
    _pkg_dir = str(_Path(__file__).parent)        # …/code_index
    _root    = str(_Path(__file__).parent.parent) # 프로젝트 루트
    # `python code_index` 실행 시 Python이 패키지 디렉토리를 sys.path[0]에
    # 추가하므로, 내부 mcp/ 폴더가 설치된 mcp 패키지와 충돌한다. 제거한다.
    if _pkg_dir in _sys.path:
        _sys.path.remove(_pkg_dir)
    if _root not in _sys.path:
        _sys.path.insert(0, _root)
    __package__ = "code_index"

import os
import subprocess
import sys
from pathlib import Path

# constants.py에서 상수들 import
from code_index import constants

def _get_arg(flag: str, default=None):
    """sys.argv 에서 'flag VALUE' 형태의 값을 반환."""
    if flag in sys.argv:
        idx = sys.argv.index(flag)
        if idx + 1 < len(sys.argv):
            return sys.argv[idx + 1]
    return default


_INDEX_ONLY       = "--index-only"       in sys.argv
_QUERY_BATCH      = "--query-batch"      in sys.argv
_HELP             = "--help"             in sys.argv
_STATUS           = "--status"           in sys.argv
_REMOVE           = "--remove"           in sys.argv
_SEARCH_CODE      = "--search-code"      in sys.argv
_GET_FILE_OUTLINE = "--get-file-outline" in sys.argv
_GET_CHUNK        = "--get-chunk"        in sys.argv
_SINGLE_QUERY     = _SEARCH_CODE or _GET_FILE_OUTLINE or _GET_CHUNK
_HTTP_PORT        = int(_get_arg("--http-port")) if "--http-port" in sys.argv else None

# 알 수 없는 옵션 감지 (-- 로 시작하는 인자 중 인식되지 않는 것)
_unknown = [a for a in sys.argv[1:] if a.startswith("--") and a not in constants.CLI_FLAGS]
if _unknown:
    print(
        f"[Error] 알 수 없는 옵션: {', '.join(_unknown)}\n"
        f"  사용법을 확인하려면: python -m code_index --help",
        file=sys.stderr,
    )
    sys.exit(1)


# ── 1. 의존성 자동 설치 ────────────────────────────────────────────────────

# 의존성 패키지 관련 상수들은 constants.py에서 import하여 사용


def _ensure_deps() -> None:
    # Python 버전 체크 - mcp 패키지는 Python 3.10+ 필요
    python_version = sys.version_info
    if python_version < constants.MIN_PYTHON_VERSION:
        print(f"[Error] Python {constants.MIN_PYTHON_VERSION[0]}.{constants.MIN_PYTHON_VERSION[1]} 이상이 필요합니다. 현재 버전: {python_version.major}.{python_version.minor}.{python_version.micro}", file=sys.stderr)
        print("해결 방법:", file=sys.stderr)
        print("  1. Python 3.10+ 설치: https://python.org/downloads", file=sys.stderr)
        print("  2. pyenv 사용: pyenv install 3.12 && pyenv global 3.12", file=sys.stderr)
        print("  3. conda 환경: conda create -n codeindex python=3.12", file=sys.stderr)
        sys.exit(1)

    missing = []
    for pkg in constants.REQUIRED_PACKAGES:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if not missing:
        if not _QUERY_BATCH:  # batch 모드는 stdout 이 JSON 전용 — 재설치/재시작 금지
            _warn_if_cpu_torch()
        return

    # torch 는 CUDA wheel 이 필요하므로 먼저 설치
    if "torch" in missing:
        missing.remove("torch")
        _install_torch()

    other = [constants.PACKAGE_INSTALL_NAMES.get(p, p) for p in missing]
    if other:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--progress-bar", "on"] + other,
        )

    print("[Setup] 패키지 설치 완료.", file=sys.stderr)


def _detect_cuda_version() -> tuple:
    """GPU 감지로 CUDA (major, minor) 반환. 없으면 (0, 0)."""
    try:
        out = subprocess.check_output(["nvidia-smi"], stderr=subprocess.STDOUT, text=True)
        
        # CUDA 버전을 더 정확히 감지
        import re
        cuda_match = re.search(r"CUDA Version: ([0-9]+)\.([0-9]+)", out)
        if cuda_match:
            major, minor = int(cuda_match.group(1)), int(cuda_match.group(2))
            print(f"[Setup] CUDA {major}.{minor} 버전 감지", file=sys.stderr)
            return (major, minor)
        
    except Exception as e:
        print(f"[Setup] nvidia-smi 실행 실패: NVIDIA 드라이버가 미설치되었거나, 환경 변수(PATH)에 등록되지 않았습니다. {e}", file=sys.stderr)

    return (0, 0)


# PyTorch 패키지 목록은 constants.py에서 사용


def _install_torch(force_reinstall: bool = False) -> None:
    """
    torch 설치 플로우:
    1. torch 설치 확인
    2. 설치되지 않은 경우: CUDA 버전 확인하고 버전에 맞는 torch 설치
    3. 설치되었으나 CPU 버전인 경우: CUDA 버전 확인하고 이전 torch 삭제 후 GPU torch 설치
    4. CUDA 버전이 설치된 경우: return
    """
    
    # 1. torch 설치 상태 확인
    torch_installed = False
    torch_has_cuda = False
    
    try:
        import torch
        torch_installed = True
        torch_has_cuda = torch.cuda.is_available()
        print(f"[Setup] torch 설치 확인: 버전={torch.__version__}, CUDA={torch_has_cuda}", file=sys.stderr)
    except ImportError:
        print("[Setup] torch가 설치되지 않았습니다.", file=sys.stderr)
    
    # 2. CUDA 버전 확인 (torch가 없거나 CPU 버전인 경우에만)
    if not torch_installed or not torch_has_cuda:
        major, minor = _detect_cuda_version()
        
        # CUDA가 없는 경우 CPU 버전으로 설치
        if major == 0:
            if torch_installed and torch_has_cuda:
                return  # 이미 CUDA 버전이 설치됨
            
            print("[Setup] CUDA 미감지 → CPU 빌드로 설치합니다.", file=sys.stderr)
            
            # CPU 버전이 이미 설치된 경우 삭제 후 재설치
            if torch_installed and not force_reinstall:
                print("[Setup] 기존 torch(CPU) 삭제 중...", file=sys.stderr)
                subprocess.check_call([sys.executable, "-m", "pip", "uninstall", "-y"] + constants.TORCH_PACKAGES)
            
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade"] + constants.TORCH_PACKAGES)
            return
        
        # CUDA 버전에 맞는 GPU torch 설치
        # 최신 CUDA 12.8을 기본으로 사용 (GeForce 3060, 4060 등 지원)
        if major >= constants.CUDA_CONFIG["preferred_version"]:
            index_url = constants.PYTORCH_CUDA_URLS["cu128"]
            cuda_label = f"cu128 (CUDA {major}.{minor})"
        elif major == constants.CUDA_CONFIG["min_major_version"] and minor >= constants.CUDA_CONFIG["min_minor_version"]:
            index_url = constants.PYTORCH_CUDA_URLS["cu118"]
            cuda_label = f"cu118 (CUDA {major}.{minor})"
        else:
            print(f"[Setup] CUDA {major}.{minor} 버전이 낮습니다 → CPU 빌드로 설치합니다.", file=sys.stderr)
            
            if torch_installed and not force_reinstall:
                print("[Setup] 기존 torch(CPU) 삭제 중...", file=sys.stderr)
                subprocess.check_call([sys.executable, "-m", "pip", "uninstall", "-y"] + constants.TORCH_PACKAGES)
            
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade"] + constants.TORCH_PACKAGES)
            return
        
        # 3. GPU torch 설치 (기존 torch가 CPU 버전인 경우 삭제 후 설치)
        if torch_installed and not torch_has_cuda and not force_reinstall:
            print("[Setup] 기존 torch(CPU) 삭제 후 GPU 버전 설치 중...", file=sys.stderr)
            subprocess.check_call([sys.executable, "-m", "pip", "uninstall", "-y"] + constants.TORCH_PACKAGES)
        
        install_cmd = [
            sys.executable, "-m", "pip", "install", "--upgrade",
            "--index-url", index_url,
        ]
        
        if force_reinstall:
            install_cmd.extend(["--force-reinstall", "--no-deps"])
            print("[Setup] 강제 재설치 모드 활성화", file=sys.stderr)
            
        install_cmd.extend(constants.TORCH_PACKAGES)
        
        print(f"[Setup] {cuda_label} GPU 빌드 설치 중 ({index_url})...", file=sys.stderr)
        
        try:
            subprocess.check_call(install_cmd)
            print(f"[Setup] torch GPU 빌드 설치 성공 ({cuda_label})", file=sys.stderr)
            
            # 설치 후 종속성 재설치 (강제 재설치 모드에서만)
            if force_reinstall:
                print("[Setup] 종속성 패키지 재설치 중...", file=sys.stderr)
                subprocess.check_call([
                    sys.executable, "-m", "pip", "install", "--upgrade",
                    "numpy", "pillow", "packaging", "sympy", "networkx", "jinja2", "fsspec"
                ])
                
        except subprocess.CalledProcessError as e:
            print(f"[Setup] GPU 빌드 설치 실패 ({e}) → CPU 빌드로 폴백합니다.", file=sys.stderr)
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade"] + constants.TORCH_PACKAGES)
    
    else:
        # 4. 이미 CUDA 버전이 설치된 경우
        print("[Setup] torch CUDA 버전이 이미 설치되어 있습니다.", file=sys.stderr)
        return


_ENV_GPU_REINSTALLED = "_MCI_GPU_REINSTALLED"


def _warn_if_cpu_torch() -> None:
    """torch CUDA 커널 테스트 및 문제 진단. 커널 실패 시 CPU 모드로 동작."""
    try:
        import torch
        
        # torch 정보 출력
        torch_version = torch.__version__
        cuda_compiled = torch.version.cuda
        print(f"[Setup] torch={torch_version}, CUDA compiled={cuda_compiled}", file=sys.stderr)
        
        if not torch.cuda.is_available():
            print("[Setup] torch.cuda.is_available() = False → CPU 모드로 동작합니다.", file=sys.stderr)
            return

        # GPU 정보 확인 및 커널 테스트
        device_count = torch.cuda.device_count()
        sm_major, sm_minor = torch.cuda.get_device_capability(0)
        gpu_name = torch.cuda.get_device_name(0)
        memory_total = torch.cuda.get_device_properties(0).total_memory // (1024**3)
        print(f"[Setup] GPU: {gpu_name} ({memory_total}GB, sm_{sm_major}{sm_minor:02d}, devices={device_count})", file=sys.stderr)

        # 실제 CUDA 커널 실행 테스트
        try:
            test_tensor = torch.tensor([1.0], device='cuda')
            result = test_tensor + torch.tensor([1.0], device='cuda')
            print(f"[Setup] CUDA 커널 테스트 성공: {result.item()}", file=sys.stderr)
            return  # 정상 동작
        except RuntimeError as e:
            print(f"[Setup] CUDA 커널 테스트 실패: {e} → CPU 모드로 동작합니다.", file=sys.stderr)
            print("[Setup] 해결방법:", file=sys.stderr)
            print("  1. NVIDIA 드라이버 재설치", file=sys.stderr)
            print("  2. CUDA Toolkit 설치 (선택적)", file=sys.stderr)
            print("  3. 시스템 재부팅", file=sys.stderr)
            return
        
    except ImportError:
        # torch 미설치 - _ensure_deps()에서 _install_torch() 호출하므로 여기서는 무시
        pass


if _HELP:
    from code_index.options import help as option
    option.help()

if _REMOVE:
    from code_index.options import remove as option
    option.remove()

_ensure_deps()


# ── 2. 설정 로드 ───────────────────────────────────────────────────────────

from code_index.config import load_config  # noqa: E402

cfg = load_config()

# --query-batch / 단일 쿼리 모드는 source_paths 없어도 동작
if not (_QUERY_BATCH or _SINGLE_QUERY):
    from code_index.config import get_all_source_paths
    _source_paths = get_all_source_paths(cfg)
    if not _source_paths:
        print(
            "[Error] config/settings.json의 indexer 설정이 비어 있습니다.\n"
            "  프로젝트별 인덱싱 설정을 추가하세요. 예:\n"
            '  "indexer": {\n'
            '    "MyProject": {\n'
            '      "source_paths": ["/path/to/source"],\n'
            '      "extensions": [".cpp", ".h", ".cs"],\n'
            '      "exclude_patterns": []\n'
            '    }\n'
            '  }',
            file=sys.stderr,
        )
        sys.exit(1)


# ── 3. 모델 다운로드 ───────────────────────────────────────────────────────

from code_index.models.model_manager import resolve_model  # noqa: E402

model_cfg = cfg["models"]
cache_dir = model_cfg.get("cache_dir", "")

# --get-file-outline / --get-chunk 는 임베딩 모델 불필요
if not (_GET_FILE_OUTLINE or _GET_CHUNK):
    print("[Setup] 임베딩 모델 확인 중...", file=sys.stderr)
    resolve_model(model_cfg["embed"], cache_dir)

    if cfg["search"].get("use_reranker", False):
        print("[Setup] 리랭커 모델 확인 중...", file=sys.stderr)
        resolve_model(model_cfg["rerank"], cache_dir)

    if cfg["vector_store"].get("mode", "server") == "server":
        from .store.qdrant_server import ensure_qdrant_server  # noqa: E402
        _qdrant_cache_root = Path(__file__).parent.parent / ".cache"
        ensure_qdrant_server(cfg["vector_store"], _qdrant_cache_root)

if _STATUS:
    from code_index.options import status as option
    option.status(cfg)

if _QUERY_BATCH:
    from code_index.options import query_batch  as option
    option.query_batch(cfg)

if _SEARCH_CODE:
    from code_index.options import search_code as option
    option.search_code(cfg)

if _GET_FILE_OUTLINE:
    from code_index.options import get_file_outline as option
    option.get_file_outline(cfg)

if _GET_CHUNK:
    from code_index.options import get_chunk as option
    option.get_chunk(cfg)

# ── 4. 인덱싱 ─────────────────────────────────────────────────────────────

from code_index.store.metadata_store import MetadataStore  # noqa: E402

vs_cfg   = cfg["vector_store"]
data_dir = vs_cfg.get("data_dir", "./data")
meta_path = os.path.join(data_dir, "metadata.db")

_meta_check = MetadataStore(meta_path)
_stats = _meta_check.stats()
_meta_check.close()

is_first_run = _stats["total_files"] == 0
mode = "전체" if is_first_run else "증분"
print(f"[Index] {mode} 인덱싱 시작...", file=sys.stderr)

from code_index.indexer.pipeline import run_index  # noqa: E402

run_index(cfg)

if _INDEX_ONLY:
    print("[Setup] --index-only 모드: MCP 서버를 시작하지 않습니다.", file=sys.stderr)
    sys.exit(0)

# ── 5. MCP 서버 ─────────────────────────────────────────────────────────

from code_index.mcp.server import start_server  # noqa: E402

start_server(cfg, http_port=_HTTP_PORT)


def main() -> None:
    """console_scripts entry point.

    모든 실행 로직은 모듈 레벨에서 처리되므로 이 함수는 비워 둡니다.
    ``pip install -e .`` 후 생성되는 ``code_index`` 명령어가 이 함수를 호출하며,
    import 시점에 이미 전체 프로그램이 실행됩니다.
    """
