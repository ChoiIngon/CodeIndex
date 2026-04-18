"""
Qdrant 독립 실행 파일 자동 다운로드 및 서버 프로세스 관리.

최초 실행 시 GitHub Releases 에서 플랫폼에 맞는 qdrant 바이너리를
.cache/qdrant/ 에 내려받고, 서브프로세스로 기동한다.
code_index 종료 시 atexit 로 자동 종료된다.
"""
from __future__ import annotations

import atexit
import os
import platform
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

QDRANT_VERSION = "v1.17.1"

_RELEASE_BASE = (
    f"https://github.com/qdrant/qdrant/releases/download/{QDRANT_VERSION}"
)

# (system, machine) → (asset 파일명, 실행 파일명)
_PLATFORM_ASSET: dict[tuple[str, str], tuple[str, str]] = {
    ("Windows", "AMD64"):  ("qdrant-x86_64-pc-windows-msvc.zip",        "qdrant.exe"),
    ("Linux",   "x86_64"): ("qdrant-x86_64-unknown-linux-musl.tar.gz",  "qdrant"),
    ("Linux",   "aarch64"):("qdrant-aarch64-unknown-linux-musl.tar.gz", "qdrant"),
    ("Darwin",  "x86_64"): ("qdrant-x86_64-apple-darwin.tar.gz",        "qdrant"),
    ("Darwin",  "arm64"):  ("qdrant-aarch64-apple-darwin.tar.gz",        "qdrant"),
}

_proc: subprocess.Popen | None = None


# ── 경로 헬퍼 ────────────────────────────────────────────────────────────────

def exe_path(cache_root: Path) -> Path:
    """플랫폼에 맞는 qdrant 실행 파일 경로를 반환한다 (존재 여부 무관)."""
    system  = platform.system()   # Windows / Linux / Darwin
    machine = platform.machine()  # AMD64 / x86_64 / arm64 / aarch64
    key = (system, machine)
    if key not in _PLATFORM_ASSET:
        raise RuntimeError(
            f"[Qdrant] 지원하지 않는 플랫폼: {system}/{machine}. "
            f"지원 목록: {list(_PLATFORM_ASSET)}"
        )
    _, exe_name = _PLATFORM_ASSET[key]
    return cache_root / "qdrant" / exe_name


# ── 다운로드 ─────────────────────────────────────────────────────────────────

def _download(cache_root: Path) -> Path:
    system  = platform.system()
    machine = platform.machine()
    key = (system, machine)
    if key not in _PLATFORM_ASSET:
        raise RuntimeError(f"[Qdrant] 지원하지 않는 플랫폼: {system}/{machine}")

    asset_name, exe_name = _PLATFORM_ASSET[key]
    qdrant_dir = cache_root / "qdrant"
    qdrant_dir.mkdir(parents=True, exist_ok=True)

    exe     = qdrant_dir / exe_name
    archive = qdrant_dir / asset_name
    url     = f"{_RELEASE_BASE}/{asset_name}"

    print(f"[Qdrant] 다운로드 중... {url}", file=sys.stderr)

    def _progress(count: int, block_size: int, total_size: int) -> None:
        if total_size > 0:
            pct = min(int(count * block_size * 100 / total_size), 100)
            print(f"\r  {pct:3d}%", end="", file=sys.stderr, flush=True)

    urlretrieve(url, archive, _progress)
    print(file=sys.stderr)

    # ── 압축 해제 ─────────────────────────────────────────────────────────────
    if asset_name.endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            names = zf.namelist()
            src = next((n for n in names if n.endswith(exe_name)), None)
            if src is None:
                raise RuntimeError(f"[Qdrant] zip 안에 {exe_name} 없음: {names}")
            data = zf.read(src)
    else:
        import tarfile
        with tarfile.open(archive) as tf:
            names = tf.getnames()
            src = next((n for n in names if n.endswith(exe_name)), None)
            if src is None:
                raise RuntimeError(f"[Qdrant] tar 안에 {exe_name} 없음: {names}")
            member = tf.extractfile(tf.getmember(src))
            data = member.read()

    exe.write_bytes(data)
    if not asset_name.endswith(".zip"):
        exe.chmod(exe.stat().st_mode | 0o111)

    archive.unlink(missing_ok=True)
    print(f"[Qdrant] 설치 완료: {exe}", file=sys.stderr)
    return exe


# ── 준비 대기 ────────────────────────────────────────────────────────────────

def _wait_ready(host: str, port: int, timeout: int = 30) -> bool:
    import urllib.error
    import urllib.request

    url      = f"http://{host}:{port}/"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False


# ── 프로세스 정리 ─────────────────────────────────────────────────────────────

def _kill_proc() -> None:
    global _proc
    if _proc and _proc.poll() is None:
        _proc.terminate()
        try:
            _proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _proc.kill()
    _proc = None


# ── 공개 API ─────────────────────────────────────────────────────────────────

def ensure_qdrant_server(vs_cfg: dict, cache_root: Path) -> None:
    """
    Qdrant 실행 파일을 확보하고 서버 프로세스를 기동한다.
    이미 실행 중이거나 외부 서버가 응답하면 기동하지 않는다.
    """
    global _proc

    host     = vs_cfg.get("host", "localhost")
    port     = int(vs_cfg.get("port", 6333))
    data_path = str(Path(vs_cfg.get("data_path", "./data/qdrant")).resolve())

    # 관리 중인 프로세스가 살아있으면 skip
    if _proc and _proc.poll() is None:
        return

    # 외부에서 이미 실행 중인지 확인
    import urllib.request
    try:
        urllib.request.urlopen(f"http://{host}:{port}/", timeout=1)
        print(f"[Qdrant] 이미 실행 중: {host}:{port}", file=sys.stderr)
        return
    except Exception:
        pass

    # 실행 파일 확보
    _exe = exe_path(cache_root)
    if not _exe.exists():
        _download(cache_root)

    # 데이터 디렉터리 보장
    Path(data_path).mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["QDRANT__STORAGE__STORAGE_PATH"] = data_path
    env["QDRANT__SERVICE__HTTP_PORT"]    = str(port)
    env["QDRANT__SERVICE__GRPC_PORT"]    = str(port + 1)
    env["QDRANT__TELEMETRY_DISABLED"]    = "true"
    env["QDRANT__LOG_LEVEL"]             = "WARN"

    print(
        f"[Qdrant] 서버 시작 중 (port={port}, data={data_path})...",
        file=sys.stderr,
    )
    _proc = subprocess.Popen(
        [str(_exe)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    atexit.register(_kill_proc)

    if not _wait_ready(host, port, timeout=30):
        _proc.terminate()
        _proc = None
        raise RuntimeError(
            f"[Qdrant] 서버 시작 실패 (30초 초과). "
            f"port {port} 가 다른 프로세스에서 사용 중인지 확인하세요."
        )

    print(f"[Qdrant] 서버 준비 완료: http://{host}:{port}", file=sys.stderr)
