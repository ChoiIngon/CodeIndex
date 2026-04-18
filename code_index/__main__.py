"""
code_index 진입점.
  1. 의존성 자동 설치
  2. 설정 로드 / source_paths 검증
  3. 모델 다운로드
  4. 인덱싱 (최초 전체 / 이후 증분)
  5. MCP 서버 시작

옵션:
  --index-only             인덱싱만 수행하고 MCP 서버를 시작하지 않음
  --remove                 설치된 패키지·모델 캐시·인덱스 데이터 삭제 (재설치 준비)
  --help                   도움말 및 MCP 설정 출력

  --search-code QUERY      자연어/심볼명으로 코드 검색 (JSON stdout)
    --top-k N              반환 결과 수
    --language LANG        언어 필터 (cpp, cs, c, ...)
    --symbol-type TYPE     심볼 타입 필터 (function, class, method, ...)

  --get-file-outline PATH  파일의 심볼 목록 반환 (JSON stdout)
  --get-chunk CHUNK_ID     청크 ID(UUID)로 코드 청크 조회 (JSON stdout)

  --query-batch            stdin JSON 배열 → stdout JSON 배열 (일괄 검색)
    --top-k N              기본 반환 결과 수
"""
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


def _print_help() -> None:
    cwd = str(Path(__file__).parent.parent.resolve()).replace("\\", "/")
    py  = sys.executable.replace("\\", "/")
    print(f"""\
MapleCodeIndex  ─  코드 시랜틱 검색 & MCP 서버

사용법:
  python -m code_index [옵션]

  --index-only        인덱싱만 수행하고 MCP 서버를 시작하지 않습니다.
  --http-port PORT    HTTP(SSE) 모드로 MCP 서버 실행 (예: --http-port 6380)
                      생략 시 stdio 모드로 실행합니다.
  --status            인덱싱 상태 출력 (프로젝트별 파일/청크 수, 최종 인덱싱 시각)
  --remove            설치된 pip 패키지, .cache/(모델+Qdrant), 인덱스 데이터를 모두 삭제합니다.
                      재설치 테스트나 완전 초기화 시 사용합니다.
  --help              이 도움말 출력

  --search-code QUERY
    자연어 또는 심볼명으로 코드를 검색합니다.
    --top-k N            반환 결과 수  (기본: settings.json search.top_k)
    --language LANG      언어 필터     (cpp / cs / c / ...)
    --symbol-type TYPE   심볼 타입   (function / class / method / ...)
    
    예:
        python -m code_index --search-code "데미지 계산 로직"
        python -m code_index --search-code "CalculateDamage" --top-k 10 --language cpp
        python -m code_index --search-code "플레이어" --symbol-type class

  --get-file-outline PATH
    파일의 심볼 목록(클래스/함수/메서드)을 반환합니다.
    PATH: 절대 경로 또는 경로 일부 (부분 매칭 지원)

    예:
        python -m code_index --get-file-outline "combat.cpp"
        python -m code_index --get-file-outline "E:/work/Project/src/player.h"

  --get-chunk CHUNK_ID
    청크 ID(UUID)로 특정 코드 청크를 조회합니다.
    CHUNK_ID: --search-code / --query-batch 결과의 chunk_id

    예:
        python -m code_index --get-chunk "fc617902-35bc-5155-b9d1-b94837fd181d"

  --query-batch
    stdin에서 JSON 배열을 읽어 일괄 검색 후 stdout에 JSON 출력.
    --top-k N   기본 반환 결과 수
      입력 포맷:
        [{{"query": "검색어", "top_k": 5}}, ...]
      예:
        echo '[{{"query":"데미지 계산","top_k":5}}]' | python -m code_index --query-batch

MCP 설정:
  settings.json 의 mcp 섹션으로 전송 방식을 선택합니다.

  ── stdio 모드 (기본, --http-port 없을 때) ──────────────────────────────
  에디터가 code_index를 자식 프로세스로 직접 실행합니다.
  에디터 1개만 사용할 때 적합합니다.

  ▶ Claude Desktop
  ├ %APPDATA%\\Claude\\claude_desktop_config.json
  └ {{
      "mcpServers": {{
        "MapleCodeIndex": {{
          "command": "{py}",
          "args": ["-m", "code_index"],
          "cwd": "{cwd}"
        }}
      }}
    }}

  ▶ VS Code / Visual Studio 2022
  └ {{
      "servers": {{
        "MapleCodeIndex": {{
          "type": "stdio",
          "command": "{py}",
          "args": ["-m", "code_index"],
          "cwd": "{cwd}"
        }}
      }}
    }}

  ── HTTP 모드 (--http-port PORT 지정 시) ────────────────────────────────
  code_index를 먼저 HTTP 서버로 실행한 뒤 여러 에디터가 URL로 접속합니다.
  에디터 여러 개 동시 사용 시 적합합니다.

  1) code_index 실행:
       python -m code_index --http-port 6380
       → [MCP] MapleCodeIndex MCP 서버 시작 (HTTP  http://127.0.0.1:6380/mcp)...

  2) 각 에디터 MCP 설정:
  ▶ Claude Desktop
  └ {{
      "mcpServers": {{
        "MapleCodeIndex": {{
          "url": "http://127.0.0.1:6380/mcp"
        }}
      }}
    }}

  ▶ VS Code / Visual Studio 2022
  └ {{
      "servers": {{
        "MapleCodeIndex": {{
          "type": "http",
          "url": "http://127.0.0.1:6380/mcp"
        }}
      }}
    }}

  ── 파일 위치 (private / global) ────────────────────────────────────────
  VS Code     private : .vscode/mcp.json  (워크스페이스 루트)
              global  : %APPDATA%\\Code\\User\\mcp.json
  VS 2022     private : .vs\\mcp.json  (솔루션 파일과 같은 폴더)
              global  : %USERPROFILE%\\.vs\\mcp.json
  Claude      공통    : %APPDATA%\\Claude\\claude_desktop_config.json
""")


# ── 1. 의존성 자동 설치 ────────────────────────────────────────────────────

_REQUIRED = [
    "torch",
    "sentencepiece",
    "einops",
    "qdrant_client",
    "grpc",
    "tree_sitter",
    "tree_sitter_cpp",
    "tree_sitter_c_sharp",
    "mcp",
]

_INSTALL_NAMES = {
    "tree_sitter": "tree-sitter>=0.22",
    "tree_sitter_cpp": "tree-sitter-cpp",
    "tree_sitter_c_sharp": "tree-sitter-c-sharp",
    "mcp": "mcp",
    "qdrant_client": "qdrant-client",
    "grpc": "grpcio",
}


def _ensure_deps() -> None:
    missing = []
    for pkg in _REQUIRED:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if not missing:
        if not _QUERY_BATCH:  # batch 모드는 stdout 이 JSON 전용 — 재설치/재시작 금지
            _warn_if_cpu_torch()
        return

    print(f"[Setup] 누락된 패키지 설치 중: {', '.join(missing)}", file=sys.stderr)

    # torch 는 CUDA wheel 이 필요하므로 먼저 설치
    if "torch" in missing:
        missing.remove("torch")
        _install_torch()

    other = [_INSTALL_NAMES.get(p, p) for p in missing]
    if other:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--progress-bar", "on"] + other,
        )

    print("[Setup] 패키지 설치 완료.", file=sys.stderr)


def _detect_cuda_version() -> tuple:
    """nvcc 로 CUDA (major, minor) 반환. 없으면 (0, 0)."""
    import re
    import shutil

    nvcc = shutil.which("nvcc")
    if not nvcc:
        base = Path(r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA")
        if base.exists():
            def _ver_key(p: Path):
                try:
                    return tuple(int(x) for x in p.name.lstrip("v").split("."))
                except ValueError:
                    return (0,)
            for ver_dir in sorted(base.iterdir(), key=_ver_key, reverse=True):
                nvcc_path = ver_dir / "bin" / "nvcc.exe"
                if nvcc_path.exists():
                    nvcc = str(nvcc_path)
                    break

    if not nvcc:
        return (0, 0)

    try:
        out = subprocess.check_output([nvcc, "--version"], stderr=subprocess.STDOUT, text=True)
        m = re.search(r"release (\d+)\.(\d+)", out)
        if m:
            return (int(m.group(1)), int(m.group(2)))
    except Exception:
        pass
    return (0, 0)


_TORCH_PKGS = ["torch", "torchvision", "torchaudio"]


def _install_torch(nightly: bool = False) -> None:
    major, minor = _detect_cuda_version()

    if major == 0:
        print("[Setup] CUDA 미감지 → CPU 빌드로 설치합니다.", file=sys.stderr)
        subprocess.check_call([sys.executable, "-m", "pip", "install"] + _TORCH_PKGS)
        return

    if nightly:
        index_url = "https://download.pytorch.org/whl/nightly/cu128"
        extra = ["--pre"]
    elif major == 12 and minor >= 8:
        index_url = "https://download.pytorch.org/whl/cu128"
        extra = []
    elif major == 12 and minor >= 4:
        index_url = "https://download.pytorch.org/whl/cu124"
        extra = []
    elif major == 12:
        index_url = "https://download.pytorch.org/whl/cu121"
        extra = []
    elif major == 11 and minor >= 8:
        index_url = "https://download.pytorch.org/whl/cu118"
        extra = []
    else:
        print("[Setup] CUDA 버전이 낮습니다 → CPU 빌드로 설치합니다.", file=sys.stderr)
        subprocess.check_call([sys.executable, "-m", "pip", "install"] + _TORCH_PKGS)
        return

    label = "nightly" if nightly else "stable"
    print(f"[Setup] CUDA {major}.{minor} 감지 → GPU {label} 빌드 설치 중 ({index_url})...", file=sys.stderr)
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "--upgrade",
            "--index-url", index_url,
        ] + extra + _TORCH_PKGS)
        print(f"[Setup] torch GPU {label} 빌드 설치 성공.", file=sys.stderr)
    except subprocess.CalledProcessError:
        print("[Setup] GPU 빌드 실패 → CPU 빌드로 폴백합니다.", file=sys.stderr)
        subprocess.check_call([sys.executable, "-m", "pip", "install"] + _TORCH_PKGS)


_ENV_GPU_REINSTALLED = "_MCI_GPU_REINSTALLED"


def _warn_if_cpu_torch() -> None:
    """torch CPU 빌드 → GPU wheel 재설치. CUDA 커널 실패 → SM 버전 기반 재설치 (1회만)."""
    try:
        import torch
        if not torch.cuda.is_available():
            major, _ = _detect_cuda_version()
            if major == 0:
                return
            if os.environ.get(_ENV_GPU_REINSTALLED):
                print("[Setup] torch GPU wheel 재설치 후에도 CUDA 미감지 → CPU 모드로 동작합니다.", file=sys.stderr)
                return
            print("[Setup] torch 가 CPU 빌드입니다. GPU wheel 로 재설치합니다...", file=sys.stderr)
            _install_torch()
            _restart_with_flag()
            return

        # GPU 정보 확인 (커널 실행 없이 드라이버 쿼리)
        sm_major, sm_minor = torch.cuda.get_device_capability(0)
        gpu_name = torch.cuda.get_device_name(0)
        print(f"[Setup] GPU: {gpu_name}  (sm_{sm_major}{sm_minor:02d})", file=sys.stderr)

        # 실제 커널 실행 테스트
        try:
            torch.tensor([1.0]).cuda() + torch.tensor([1.0]).cuda()
            return  # 정상
        except RuntimeError:
            pass

        if os.environ.get(_ENV_GPU_REINSTALLED):
            print("[Setup] GPU 빌드 재설치 후에도 커널 실패 → CPU 모드로 동작합니다.", file=sys.stderr)
            return

        # sm_100+ (Blackwell 등) stable 미지원 가능 → nightly
        nightly = sm_major >= 10
        label = "nightly" if nightly else "stable"
        print(
            f"[Setup] CUDA 커널 실패 (sm_{sm_major}{sm_minor:02d}) "
            f"→ {label} GPU 빌드로 재설치합니다...",
            file=sys.stderr,
        )
        _install_torch(nightly=nightly)
        _restart_with_flag()
    except ImportError:
        pass


def _restart_with_flag() -> None:
    """재설치 완료 후 무한 루프 방지 플래그를 환경 변수로 설정하고 재시작."""
    print("[Setup] 재설치 완료. 재시작합니다...", file=sys.stderr)
    new_env = os.environ.copy()
    new_env[_ENV_GPU_REINSTALLED] = "1"
    os.execve(sys.executable, [sys.executable] + sys.argv, new_env)


def _do_remove() -> None:
    """설치된 패키지, 모델 캐시, 인덱스 데이터를 삭제한다."""
    import json
    import shutil

    print("[Remove] 다음 항목을 삭제합니다:", file=sys.stderr)
    print("  - pip 패키지 (torch, sentence-transformers, qdrant-client, tree-sitter 등)", file=sys.stderr)
    print("  - .cache/ (모델 캐시 + Qdrant 실행 파일)", file=sys.stderr)
    print("  - 인덱스 데이터 (벡터 DB, 메타데이터 DB, 임베딩 캐시)", file=sys.stderr)
    answer = input("  계속하시겠습니까? [y/N] ").strip().lower()
    if answer not in ("y", "yes"):
        print("[Remove] 취소했습니다.", file=sys.stderr)
        sys.exit(0)

    # settings.json 에서 경로 직접 로드 (패키지 의존 없이)
    _settings_path = Path(__file__).parent.parent / "config" / "settings.json"
    try:
        with open(_settings_path, encoding="utf-8") as _f:
            _settings = json.load(_f)
    except Exception:
        _settings = {}

    _vs_cfg    = _settings.get("vector_store", {})
    _model_cfg = _settings.get("models", {})

    # ── 인덱스 데이터 경로 계산 ──────────────────────────────────────────────
    _data_dir = Path(_vs_cfg.get("data_path", "./data/qdrant"))
    if not _data_dir.is_absolute():
        _data_dir = (Path(__file__).parent.parent / _data_dir).resolve()
    _data_parent = _data_dir.parent

    _index_paths = [
        _data_dir,
        _data_parent / "metadata.db",
        _data_parent / "embed_cache.db",
    ]

    print("[Remove] 인덱스 데이터 삭제 중...", file=sys.stderr)
    for _p in _index_paths:
        if _p.exists():
            if _p.is_dir():
                shutil.rmtree(_p)
            else:
                _p.unlink()
            print(f"  삭제: {_p}", file=sys.stderr)
        else:
            print(f"  건너뜀 (없음): {_p}", file=sys.stderr)

    # ── 모델 캐시 삭제 ────────────────────────────────────────────────────────
    _cache_dir = _model_cfg.get("cache_dir", "").strip()

    # cache_dir 미설정 시 프로젝트 루트 .cache 가 기본값
    _default_cache = Path(__file__).parent.parent / ".cache"
    _resolved_cache = Path(_cache_dir) if _cache_dir else _default_cache

    print("[Remove] 모델 캐시 삭제 중...", file=sys.stderr)
    if _resolved_cache.exists():
        shutil.rmtree(_resolved_cache)
        print(f"  삭제: {_resolved_cache}", file=sys.stderr)
    else:
        print(f"  건너뜀 (없음): {_resolved_cache}", file=sys.stderr)

    # ── pip 패키지 언인스톨 ───────────────────────────────────────────────────
    print("[Remove] pip 패키지 언인스톨 중...", file=sys.stderr)
    _uninstall_pkgs = list(_TORCH_PKGS) + [_INSTALL_NAMES.get(p, p) for p in _REQUIRED]
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "uninstall", "-y"] + _uninstall_pkgs,
        )
        print("[Remove] 패키지 언인스톨 완료.", file=sys.stderr)
    except subprocess.CalledProcessError as _e:
        print(f"[Remove] 패키지 언인스톨 중 오류 발생: {_e}", file=sys.stderr)

    print("", file=sys.stderr)
    print("[Remove] 완료. 재설치하려면 'python -m code_index' 를 다시 실행하세요.", file=sys.stderr)
    sys.exit(0)


if _HELP:
    _print_help()
    sys.exit(0)

if _REMOVE:
    _do_remove()

if _STATUS:
    import os
    from datetime import datetime, timezone

    from .config import load_config as _load_cfg
    from .store.metadata_store import MetadataStore as _MS

    _cfg      = _load_cfg()
    _vs_cfg   = _cfg["vector_store"]
    _data_dir = _vs_cfg.get("data_path", "./data/qdrant")
    _meta_path  = os.path.join(os.path.dirname(_data_dir), "metadata.db")
    _cache_path = os.path.join(os.path.dirname(_data_dir), "embed_cache.db")
    _source_paths = _cfg["indexer"].get("source_paths", [])

    _meta = _MS(_meta_path)
    _total = _meta.stats()
    _proj  = _meta.project_stats(_source_paths)
    _meta.close()

    def _fmt_dt(iso: str) -> str:
        if not iso:
            return "(없음)"
        try:
            dt = datetime.fromisoformat(iso).astimezone()
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return iso

    print("=" * 60)
    print("  MapleCodeIndex  인덱싱 상태")
    print("=" * 60)
    print(f"  전체 파일 : {_total['total_files']:,}개")
    print(f"  전체 청크 : {_total['total_chunks']:,}개")
    print(f"  메타 DB   : {_meta_path}")
    print(f"  임베딩 캐시: {_cache_path}")
    _qdrant_mode = _vs_cfg.get("mode", "server")
    if _qdrant_mode == "server":
        _q_host = _vs_cfg.get("host", "localhost")
        _q_port = _vs_cfg.get("port", 6333)
        _q_cache = Path(__file__).parent.parent / ".cache"
        _q_exe_name = "qdrant.exe" if sys.platform == "win32" else "qdrant"
        _q_exe = _q_cache / "qdrant" / _q_exe_name
        _q_ready = "준비됨" if _q_exe.exists() else "미설치 (최초 실행 시 자동 다운로드)"
        print(f"  벡터 DB   : server mode  ({_q_host}:{_q_port})")
        print(f"  Qdrant exe: {_q_exe}  [{_q_ready}]")
    else:
        print(f"  벡터 DB   : embedded mode  ({_data_dir})")
    _debug    = _cfg.get("debug", False)
    _log_path = str(Path("log.txt").resolve())
    _model_cache_dir = _cfg.get("models", {}).get("cache_dir", "").strip()
    if not _model_cache_dir:
        _model_cache_dir = str((Path(__file__).parent.parent / ".cache").resolve())
    print(f"  모델 캐시 : {_model_cache_dir}")
    print(f"  MCP 전송  : stdio (SSE 사용 시 --http-port PORT 로 실행)")
    print(f"  로그 파일 : {_log_path}  ({'debug=true' if _debug else 'debug=false, 비활성'})")
    print()
    if not _source_paths:
        print("  등록된 source_paths 없음 (config/settings.json 확인)")
    else:
        print(f"  {'프로젝트 경로':<45} {'파일':>6} {'청크':>7}  최종 인덱싱")
        print("  " + "-" * 78)
        for p in _proj:
            sp   = p["source_path"]
            disp = (sp[:42] + "...") if len(sp) > 45 else sp
            print(f"  {disp:<45} {p['files']:>6,} {p['chunks']:>7,}  {_fmt_dt(p['last_indexed'])}")
    print("=" * 60)
    sys.exit(0)

_ensure_deps()


# ── 2. 설정 로드 ───────────────────────────────────────────────────────────

from .config import load_config  # noqa: E402

cfg = load_config()

# --query-batch / 단일 쿼리 모드는 source_paths 없어도 동작
if not (_QUERY_BATCH or _SINGLE_QUERY):
    _source_paths = cfg["indexer"].get("source_paths", [])
    if not _source_paths:
        print(
            "[Error] config/settings.json 의 indexer.source_paths 가 비어 있습니다.\n"
            "  인덱싱할 소스 경로를 추가하세요. 예:\n"
            '  "source_paths": ["C:/Project/src"]',
            file=sys.stderr,
        )
        sys.exit(1)


# ── 3. 모델 다운로드 ───────────────────────────────────────────────────────

from .models.model_manager import resolve_model  # noqa: E402

model_cfg = cfg["models"]
cache_dir = model_cfg.get("cache_dir", "")

# --get-file-outline / --get-chunk 는 임베딩 모델 불필요
if not (_GET_FILE_OUTLINE or _GET_CHUNK):
    print("[Setup] 임베딩 모델 확인 중...", file=sys.stderr)
    resolve_model(model_cfg["embed"], cache_dir)

    if cfg["search"].get("use_reranker", False):
        print("[Setup] 리랭커 모델 확인 중...", file=sys.stderr)
        resolve_model(model_cfg["rerank"], cache_dir)


# ── 4. Qdrant 서버 기동 (server mode 일 때) ──────────────────────────────────

if not (_GET_FILE_OUTLINE or _GET_CHUNK):
    if cfg["vector_store"].get("mode", "server") == "server":
        from .store.qdrant_server import ensure_qdrant_server  # noqa: E402
        _qdrant_cache_root = Path(__file__).parent.parent / ".cache"
        ensure_qdrant_server(cfg["vector_store"], _qdrant_cache_root)


# ── query-batch 모드 ────────────────────────────────────────────────────────

if _QUERY_BATCH:
    import json
    import os

    from .indexer.embedder import Embedder
    from .retriever.hybrid_search import hybrid_search
    from .store.cache import EmbedCache
    from .store.metadata_store import MetadataStore
    from .store.vector_store import VectorStore

    # --top-k 파싱
    _top_k = cfg["search"].get("top_k", 20)
    if "--top-k" in sys.argv:
        _top_k = int(sys.argv[sys.argv.index("--top-k") + 1])

    vs_cfg  = cfg["vector_store"]
    emb_cfg = cfg["embedding"]
    data_dir  = vs_cfg.get("data_path", "./data/qdrant")
    meta_path  = os.path.join(os.path.dirname(data_dir), "metadata.db")
    cache_path = os.path.join(os.path.dirname(data_dir), "embed_cache.db")

    _metadata     = MetadataStore(meta_path)
    _cache        = EmbedCache(cache_path)
    _vector_store = VectorStore(vs_cfg, emb_cfg["vector_size"])
    _embed_path   = resolve_model(model_cfg["embed"], cache_dir)
    _embedder     = Embedder(_embed_path, emb_cfg, _cache)

    # Windows에서 sys.stdin 기본 인코딩(cp949)으로 UTF-8 한국어가 손상되는 것을 방지
    _queries = json.loads(sys.stdin.buffer.read())
    _output  = []

    for item in _queries:
        q      = item["query"]
        top_k  = item.get("top_k", _top_k)
        vec    = _embedder.embed_query(q)
        hits   = hybrid_search(
            query_vec=vec,
            query_text=q,
            metadata=_metadata,
            vector_store=_vector_store,
            top_k=top_k,
            alpha=cfg["search"].get("alpha", 0.7),
        )
        _output.append({
            "query": q,
            "results": [
                {
                    "chunk_id":    r.chunk_id,
                    "score":       round(r.score, 6),
                    "file_path":   r.file_path,
                    "symbol_name": r.symbol_name,
                    "symbol_type": r.symbol_type,
                    "start_line":  r.start_line,
                    "end_line":    r.end_line,
                    "content":     r.content[:1000],
                }
                for r in hits
            ],
        })

    sys.stdout.buffer.write(json.dumps(_output, ensure_ascii=False).encode('utf-8'))
    sys.stdout.buffer.write(b'\n')
    _metadata.close()
    _cache.close()
    _vector_store.close()
    sys.exit(0)


# ── search-code 모드 ────────────────────────────────────────────────────────

if _SEARCH_CODE:
    import json
    import os

    from .indexer.embedder import Embedder
    from .retriever.hybrid_search import hybrid_search
    from .store.cache import EmbedCache
    from .store.metadata_store import MetadataStore
    from .store.vector_store import VectorStore

    _query = _get_arg("--search-code")
    if not _query:
        print("[Error] --search-code 다음에 검색어를 입력하세요.", file=sys.stderr)
        sys.exit(1)

    _top_k       = int(_get_arg("--top-k", cfg["search"].get("top_k", 20)))
    _language    = _get_arg("--language", "")
    _symbol_type = _get_arg("--symbol-type", "")

    vs_cfg   = cfg["vector_store"]
    emb_cfg  = cfg["embedding"]
    data_dir = vs_cfg.get("data_path", "./data/qdrant")
    meta_path  = os.path.join(os.path.dirname(data_dir), "metadata.db")
    cache_path = os.path.join(os.path.dirname(data_dir), "embed_cache.db")

    _metadata     = MetadataStore(meta_path)
    _cache        = EmbedCache(cache_path)
    _vector_store = VectorStore(vs_cfg, emb_cfg["vector_size"])
    _embed_path   = resolve_model(model_cfg["embed"], cache_dir)
    _embedder     = Embedder(_embed_path, emb_cfg, _cache)

    _filters: dict = {}
    if _language:
        _filters["language"] = _language
    if _symbol_type:
        _filters["symbol_type"] = _symbol_type

    _vec  = _embedder.embed_query(_query)
    _hits = hybrid_search(
        query_vec=_vec,
        query_text=_query,
        metadata=_metadata,
        vector_store=_vector_store,
        top_k=_top_k,
        alpha=cfg["search"].get("alpha", 0.7),
        filters=_filters or None,
    )
    _result = [
        {
            "chunk_id":    r.chunk_id,
            "score":       round(r.score, 6),
            "file_path":   r.file_path,
            "symbol_name": r.symbol_name,
            "symbol_type": r.symbol_type,
            "start_line":  r.start_line,
            "end_line":    r.end_line,
            "content":     r.content[:1000],
        }
        for r in _hits
    ]
    sys.stdout.buffer.write(json.dumps(_result, ensure_ascii=False, indent=2).encode("utf-8"))
    sys.stdout.buffer.write(b"\n")
    _metadata.close()
    _cache.close()
    _vector_store.close()
    sys.exit(0)


# ── get-file-outline 모드 ───────────────────────────────────────────────────

if _GET_FILE_OUTLINE:
    import json
    import os

    from .store.metadata_store import MetadataStore

    _path = _get_arg("--get-file-outline")
    if not _path:
        print("[Error] --get-file-outline 다음에 파일 경로를 입력하세요.", file=sys.stderr)
        sys.exit(1)

    vs_cfg   = cfg["vector_store"]
    data_dir = vs_cfg.get("data_path", "./data/qdrant")
    meta_path = os.path.join(os.path.dirname(data_dir), "metadata.db")

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


# ── get-chunk 모드 ──────────────────────────────────────────────────────────

if _GET_CHUNK:
    import json
    import os

    from .store.metadata_store import MetadataStore

    _chunk_id = _get_arg("--get-chunk")
    if not _chunk_id:
        print("[Error] --get-chunk 다음에 청크 ID(UUID)를 입력하세요.", file=sys.stderr)
        sys.exit(1)

    vs_cfg   = cfg["vector_store"]
    data_dir = vs_cfg.get("data_path", "./data/qdrant")
    meta_path = os.path.join(os.path.dirname(data_dir), "metadata.db")

    _metadata = MetadataStore(meta_path)
    _chunk    = _metadata.get_chunk(_chunk_id)
    _metadata.close()

    if not _chunk:
        print(f"[Error] 청크를 찾을 수 없습니다: {_chunk_id}", file=sys.stderr)
        sys.exit(1)

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


# ── 4. 인덱싱 ─────────────────────────────────────────────────────────────

from .store.metadata_store import MetadataStore  # noqa: E402

vs_cfg   = cfg["vector_store"]
data_dir = vs_cfg.get("data_path", "./data/qdrant")
meta_path = os.path.join(os.path.dirname(data_dir), "metadata.db")

_meta_check = MetadataStore(meta_path)
_stats = _meta_check.stats()
_meta_check.close()

is_first_run = _stats["total_files"] == 0
mode = "전체" if is_first_run else "증분"
print(f"[Index] {mode} 인덱싱 시작...", file=sys.stderr)

from .indexer.pipeline import run_index  # noqa: E402

run_index(cfg)

if _INDEX_ONLY:
    print("[Setup] --index-only 모드: MCP 서버를 시작하지 않습니다.", file=sys.stderr)
    sys.exit(0)


# ── 5. MCP 서버 ─────────────────────────────────────────────────────────

from .mcp.server import start_server  # noqa: E402

start_server(cfg, http_port=_HTTP_PORT)
