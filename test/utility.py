from enum import IntEnum
import sys
import time

_VERBOSE: bool = False


def set_verbose(value: bool) -> None:
    global _VERBOSE
    _VERBOSE = value

class LogLevel(IntEnum):
    VERBOSE = 0
    INFO    = 1
    ERROR   = 2

# ── 성능 측정 유틸리티 ──────────────────────────────────────────────────────────
class Timer:
    def __init__(self, name: str):
        self.name = name
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        log_verbose(f"{self.name} 시작...")
        return self
    
    def __exit__(self, *args):
        if self.start_time:
            elapsed = time.time() - self.start_time
            log_info(f"{self.name} 완료 ({elapsed:.2f}s)")

def log_info(msg: str, prefix: str = "정보") -> None:
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] [{prefix}] {msg}")

def log_error(msg: str, prefix: str = "오류") -> None:
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] [{prefix}] {msg}", file=sys.stderr)

def log_verbose(msg: str, prefix: str = "상세") -> None:
    if _VERBOSE:
        timestamp = time.strftime("%H:%M:%S")
        print(f"[{timestamp}] [{prefix}] {msg}")