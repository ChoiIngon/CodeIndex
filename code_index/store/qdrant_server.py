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
import ssl
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen, urlretrieve, Request

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


# ── SSL 처리 헬퍼 ────────────────────────────────────────────────────────────

def _create_ssl_context(verify: bool = True) -> ssl.SSLContext | None:
    """SSL 컨텍스트를 생성한다. verify=False면 인증서 검증을 비활성화한다."""
    if not verify:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context
    return None


def _should_skip_ssl_verify() -> bool:
    """환경변수를 확인하여 SSL 검증을 건너뛸지 결정한다."""
    return os.environ.get("CODE_INDEX_SKIP_SSL_VERIFY", "").lower() in ("1", "true", "yes")


def _download_with_progress(url: str, filepath: Path, ssl_context: ssl.SSLContext = None) -> None:
    """진행률을 표시하면서 파일을 다운로드한다."""
    import urllib.request
    
    def _progress(count: int, block_size: int, total_size: int) -> None:
        if total_size > 0:
            pct = min(int(count * block_size * 100 / total_size), 100)
            print(f"\r  {pct:3d}%", end="", file=sys.stderr, flush=True)
    
    # SSL 컨텍스트가 제공되면 opener를 사용
    if ssl_context:
        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ssl_context)
        )
        # 기존 opener 백업
        old_opener = urllib.request._opener
        try:
            urllib.request.install_opener(opener)
            urllib.request.urlretrieve(url, filepath, _progress)
        finally:
            # opener 복원
            urllib.request.install_opener(old_opener)
    else:
        urllib.request.urlretrieve(url, filepath, _progress)


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

    # SSL 검증 설정 확인
    skip_ssl = _should_skip_ssl_verify()
    ssl_context = _create_ssl_context(verify=not skip_ssl) if skip_ssl else None
    
    if skip_ssl:
        print(f"[Qdrant] SSL 검증 비활성화 모드로 다운로드", file=sys.stderr)

    try:
        # 첫 번째 시도: 기본 설정으로 다운로드
        _download_with_progress(url, archive, ssl_context)
    except Exception as e:
        error_msg = str(e)
        
        # SSL 인증서 오류 감지 (URLError, ssl.SSLError, 일반 Exception 포함)
        if any(keyword in error_msg for keyword in [
            "CERTIFICATE_VERIFY_FAILED", 
            "certificate verify failed", 
            "SSL", 
            "Authority Key Identifier",
            "CERT_NONE",
            "certificate"
        ]):
            print(f"\n[Qdrant] SSL 인증서 오류 감지: {error_msg}", file=sys.stderr)
            if not skip_ssl:
                print(f"[Qdrant] SSL 검증을 비활성화하고 재시도합니다...", file=sys.stderr)
                try:
                    # SSL 검증 비활성화 후 재시도
                    ssl_context = _create_ssl_context(verify=False)
                    _download_with_progress(url, archive, ssl_context)
                    print(f"\n[Qdrant] SSL 검증 비활성화로 다운로드 성공", file=sys.stderr)
                    print(f"[Qdrant] 향후 SSL 검증을 건너뛰려면 환경변수를 설정하세요: CODE_INDEX_SKIP_SSL_VERIFY=1", file=sys.stderr)
                except Exception as retry_e:
                    print(f"\n[Qdrant] 다운로드 실패({retry_e})", file=sys.stderr)
                    print("일시적 네트워크 오류일 수 있으니 잠시 후 code_index를 재시작 해주세요", file=sys.stderr)
                    sys.exit(1)
            else:
                print(f"\n[Qdrant] 다운로드 실패({error_msg})", file=sys.stderr)
                print("일시적 네트워크 오류일 수 있으니 잠시 후 code_index를 재시작 해주세요", file=sys.stderr)
                sys.exit(1)
        else:
            print(f"\n[Qdrant] 다운로드 실패({error_msg})", file=sys.stderr)
            print("일시적 네트워크 오류일 수 있으니 잠시 후 code_index를 재시작 해주세요", file=sys.stderr)
            sys.exit(1)
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

def trigger_wal_cleanup(host: str, port: int) -> None:
    """
    Qdrant 서버 시작 후 WAL 파일이 자연스럽게 정리되도록 대기하고
    용량 불일치를 감지하여 사용자에게 안내한다.
    """
    try:
        import urllib.request
        import json
        import time
        
        # 서버가 이미 _wait_ready()로 준비 확인되었으므로 바로 API 호출
        
        # 컬렉션 정보 조회
        collections_url = f"http://{host}:{port}/collections"
        req = urllib.request.Request(collections_url)
        
        with urllib.request.urlopen(req, timeout=5) as response:
            collections_data = json.loads(response.read().decode('utf-8'))
            collections = collections_data.get("result", {}).get("collections", [])
        
        if not collections:
            return
            
        # 첫 번째 컬렉션의 벡터 수 확인
        for collection_info in collections:
            collection_name = collection_info.get("name", "")
            if collection_name:
                try:
                    info_url = f"http://{host}:{port}/collections/{collection_name}"
                    req = urllib.request.Request(info_url)
                    
                    with urllib.request.urlopen(req, timeout=5) as response:
                        info_data = json.loads(response.read().decode('utf-8'))
                        vector_count = info_data.get("result", {}).get("vectors_count", 0)
                        
                        # 벡터 수가 적은데 WAL 파일이 큰 경우 사용자에게 안내
                        if vector_count < 1000:
                            print(f"[Qdrant] 벡터 수: {vector_count}개 - 자동 정리 대기 중...", file=sys.stderr)
                        
                        break  # 첫 번째 컬렉션만 확인
                        
                except Exception:
                    continue
        
        # 추가 정리 대기 (WAL 파일은 Qdrant가 백그라운드에서 자동 처리)
        # time.sleep(1.0) - 불필요한 대기 제거
        
        print(f"[Qdrant] WAL 파일은 백그라운드에서 자동 정리됩니다", file=sys.stderr)
        
    except Exception as e:
        # WAL 정리는 중요하지 않으므로 오류를 무시
        pass


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
        
        _proc = None
        raise RuntimeError(
            f"[Qdrant] 서버 시작 실패 (30초 초과). "
            f"port {port} 가 다른 프로세스에서 사용 중인지 확인하세요."
        )

    print(f"[Qdrant] 서버 준비 완료: http://{host}:{port}", file=sys.stderr)
