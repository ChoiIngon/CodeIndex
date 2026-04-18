from __future__ import annotations

import json
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


class DebugLogger:
    """MCP 요청/응답을 log.txt 에 기록하는 단순 로거."""

    def __init__(self, log_path: str = "log.txt", echo_stderr: bool = False):
        self._path = Path(log_path)
        self._echo = echo_stderr
        self._lock = threading.Lock()

    def _ts(self) -> str:
        now = datetime.now()
        return now.strftime("%Y-%m-%d %H:%M:%S.") + f"{now.microsecond // 1000:03d}"

    def _write(self, tag: str, tool: str, data: Any) -> None:
        try:
            body = json.dumps(data, ensure_ascii=False, indent=2)
        except Exception:
            body = str(data)
        line = f"[{self._ts()}] [{tag}] {tool}\n{body}\n{'-' * 60}\n"
        with self._lock:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line)
            if self._echo:
                print(line, end="", file=sys.stderr)

    def log_input(self, tool: str, kwargs: dict) -> None:
        self._write("INPUT", tool, kwargs)

    def log_output(self, tool: str, result: Any) -> None:
        self._write("OUTPUT", tool, result)
