"""
CodeIndex 자식 프로세스 관리 클래스
"""
from __future__ import annotations

import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

ROOT = Path(__file__).parent.parent.resolve()

_JSONRPC_VERSION = "2.0"
_MCP_PROTOCOL_VERSION = "2024-11-05"


class CodeIndexProcess:
    """'python -m code_index' 자식 프로세스를 MCP stdio 클라이언트로 관리."""

    def __init__(self) -> None:
        self.pid: Optional[int] = None
        self._process: Optional[subprocess.Popen] = None
        self._req_id = 0
        self._stdout_q: queue.Queue = queue.Queue()
        self.last_stderr: str = ""  # 마지막 실행의 stderr 출력 (wait=True 시)

    # ── 실행 ─────────────────────────────────────────────────────────────────

    def run(
        self,
        options: Union[str, List[str], None] = None,
        wait: bool = True,
    ) -> Optional[int]:
        """'python -m code_index {options}' 를 자식 프로세스로 실행합니다.

        Args:
            options: 전달할 옵션. 예) "--index-only" 또는 ["--search", "query"]
            wait:    True  → 종료까지 대기 후 returncode 반환.
                     False → MCP stdio 핸드셰이크 완료 후 PID 반환.

        Returns:
            wait=True  → returncode. wait=False → PID. 실패 시 None.
        """
        cmd = [sys.executable, "-m", "code_index"]
        if options:
            cmd.extend(options.split() if isinstance(options, str) else options)

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        try:
            self._process = subprocess.Popen(
                cmd,
                cwd=str(ROOT),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
        except Exception as e:
            print(f"[오류] 프로세스 시작 실패: {e}", file=sys.stderr)
            return None

        self.pid = self._process.pid

        if wait:
            # communicate()로 stdout/stderr를 모두 소비 — 파이프 버퍼 블록 방지
            _, stderr_out = self._process.communicate()
            self.last_stderr = stderr_out or ""
            rc = self._process.returncode
            self._process = None
            self.pid = None
            return rc

        # ── MCP stdio 모드 ────────────────────────────────────────────────
        # stderr 드레인: 파이프 버퍼가 꽉 차 서버가 블록되는 것을 방지
        threading.Thread(target=self._drain_stderr, daemon=True).start()
        # stdout 리더: JSON 메시지를 큐에 적재
        threading.Thread(target=self._read_stdout, daemon=True).start()

        # initialize 메시지를 즉시 stdin 파이프 버퍼에 기록한다.
        # FastMCP event loop가 시작(모델 로드 완료 후)되면 버퍼에서 읽어 처리한다.
        # 모델 로드 시간(수십 초)을 수용하도록 타임아웃을 넉넉하게 설정한다.
        if not self._mcp_handshake(timeout=300.0):
            print("[오류] MCP 핸드셰이크 실패", file=sys.stderr)
            self.kill()
            return None

        return self.pid

    # ── 백그라운드 스레드 ─────────────────────────────────────────────────────

    def _drain_stderr(self) -> None:
        """stderr를 지속적으로 소비해 서버 블로킹을 방지합니다."""
        try:
            for _ in self._process.stderr:
                pass
        except Exception:
            pass

    def _read_stdout(self) -> None:
        """stdout의 JSON 줄을 큐에 적재합니다."""
        try:
            for line in self._process.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    self._stdout_q.put(json.loads(line))
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass

    # ── MCP JSON-RPC 내부 메서드 ──────────────────────────────────────────────

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    def _send(self, obj: Dict[str, Any]) -> bool:
        """JSON-RPC 메시지를 자식 프로세스 stdin에 전송합니다."""
        try:
            self._process.stdin.write(json.dumps(obj, ensure_ascii=False) + "\n")
            self._process.stdin.flush()
            return True
        except Exception as e:
            print(f"[오류] 전송 실패: {e}", file=sys.stderr)
            return False

    def _recv(self, req_id: int, timeout: float) -> Optional[Dict[str, Any]]:
        """지정한 id의 JSON-RPC 응답이 올 때까지 대기합니다."""
        deadline = time.monotonic() + timeout
        skipped: List[Dict] = []
        try:
            while True:
                if self._process and self._process.poll() is not None:
                    return None
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                try:
                    msg = self._stdout_q.get(timeout=min(remaining, 0.5))
                except queue.Empty:
                    continue
                if msg.get("id") == req_id:
                    return msg
                skipped.append(msg)
        finally:
            for m in skipped:
                self._stdout_q.put(m)

    def _mcp_handshake(self, timeout: float = 300.0) -> bool:
        """MCP JSON-RPC 2.0 초기화 핸드셰이크를 수행합니다.

        initialize 메시지를 stdin 파이프에 즉시 적재합니다.
        FastMCP event loop가 시작되면 버퍼에서 읽어 응답합니다.
        모델 로드 시간을 포함해 timeout 내에 응답이 오지 않으면 실패로 처리합니다.
        """
        req_id = self._next_id()

        if not self._send({
            "jsonrpc": _JSONRPC_VERSION,
            "id": req_id,
            "method": "initialize",
            "params": {
                "protocolVersion": _MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "CodeIndexTestClient", "version": "1.0.0"},
            },
        }):
            return False

        resp = self._recv(req_id, timeout=timeout)
        if resp is None:
            print("[오류] initialize 응답 타임아웃", file=sys.stderr)
            return False
        if "error" in resp:
            print(f"[오류] initialize 오류: {resp['error']}", file=sys.stderr)
            return False

        # initialized 알림 전송 (응답 없음)
        self._send({
            "jsonrpc": _JSONRPC_VERSION,
            "method": "initialized",
            "params": {},
        })

        # Qdrant gRPC 포트(6334)가 실제로 응답할 때까지 대기.
        # AI 클라이언트는 이미 실행 중인 서버에 접속하므로 gRPC가 준비돼 있지만,
        # 신규 프로세스에서는 MCP init 직후 gRPC가 아직 준비되지 않을 수 있다.
        self._wait_grpc_ready()

        return True

    def _wait_grpc_ready(
        self,
        host: str = "localhost",
        grpc_port: int = 6334,
        timeout: float = 30.0,
    ) -> bool:
        """Qdrant gRPC 포트가 HTTP/2 응답을 반환할 때까지 대기합니다."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with socket.create_connection((host, grpc_port), timeout=1.0) as s:
                    s.sendall(b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n")
                    s.settimeout(1.0)
                    if s.recv(9):
                        return True
            except (OSError, socket.timeout):
                pass
            time.sleep(0.3)
        print(f"[경고] Qdrant gRPC({host}:{grpc_port}) 응답 없음 — HTTP 모드로 동작", file=sys.stderr)
        return False

    # ── MCP 툴 호출 ──────────────────────────────────────────────────────────

    def search_code(
        self,
        query: str,
        top_k: int = 20,
        language: str = "",
        symbol_type: str = "",
        project: str = "",
        timeout: float = 30.0,
    ) -> Optional[List[Dict[str, Any]]]:
        """MCP 서버의 search_code 툴을 호출합니다.

        Args:
            query:       검색 쿼리.
            top_k:       최대 결과 수 (기본 20).
            language:    언어 필터 (예: "cpp", "cs").
            symbol_type: 심볼 타입 필터 (예: "function", "class").
            project:     프로젝트 필터.
            timeout:     응답 대기 시간(초).

        Returns:
            검색 결과 dict 리스트. 실패 시 None.
        """
        req_id = self._next_id()

        if not self._send({
            "jsonrpc": _JSONRPC_VERSION,
            "id": req_id,
            "method": "tools/call",
            "params": {
                "name": "search_code",
                "arguments": {
                    "query": query,
                    "top_k": top_k,
                    "language": language,
                    "symbol_type": symbol_type,
                    "project": project,
                },
            },
        }):
            return None

        resp = self._recv(req_id, timeout=timeout)
        if resp is None:
            print("[오류] search_code 응답 타임아웃", file=sys.stderr)
            return None
        if "error" in resp:
            print(f"[오류] search_code 오류: {resp['error']}", file=sys.stderr)
            return None

        # FastMCP 응답 구조: result.content 는 {"type":"text","text":"<json>"} 항목의 리스트
        # 각 항목의 text 가 개별 결과 dict의 JSON 직렬화 문자열
        try:
            content = resp.get("result", {}).get("content", [])
            results = []
            for entry in content:
                text = entry.get("text", "")
                if text.startswith("Error"):
                    print(f"[오류] 서버 오류: {text[:300]}", file=sys.stderr)
                    return None
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, list):
                        results.extend(parsed)
                    elif isinstance(parsed, dict):
                        results.append(parsed)
                except json.JSONDecodeError:
                    pass
            return results
        except Exception as e:
            print(f"[오류] 응답 파싱 실패: {e}", file=sys.stderr)
            return None

    # ── 종료 및 상태 ─────────────────────────────────────────────────────────

    def kill(self) -> bool:
        """자식 프로세스를 강제 종료합니다."""
        if self._process is None:
            return False
        try:
            if self._process.poll() is None:
                if sys.platform == "win32":
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(self._process.pid)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
                    )
                else:
                    self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait()
            self._process = None
            self.pid = None
            return True
        except Exception as e:
            print(f"[오류] 종료 실패: {e}", file=sys.stderr)
            return False

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None


# ── 테스트 ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    child = CodeIndexProcess()

    # 1단계: 인덱싱 완료까지 대기
    print("[테스트] 인덱싱 중...")
    child.run("--index-only", wait=True)

    # 2단계: MCP 서버 시작 + 핸드셰이크 (모델 로드 포함, 최대 300초 대기)
    print("[테스트] MCP 서버 시작 중...")
    child.run(wait=False)
    print("[테스트] search_code 호출 중...")
    result = child.search_code("패킷 처리")

    if result is None:
        print("검색 실패 또는 결과 없음")
    else:
        print(f"검색 결과: {len(result)}건")
        for i, item in enumerate(result, 1):
            print(f"\n[{i}] {item.get('symbol_name', '')} ({item.get('symbol_type', '')})")
            print(f"  파일    : {item.get('file_path', '')}")
            print(f"  라인    : {item.get('start_line', '')}-{item.get('end_line', '')}")
            print(f"  언어    : {item.get('language', '')}")
            print(f"  프로젝트: {item.get('project_name', '')}")
            print(f"  점수    : {item.get('score', '')}")
            content = item.get("content", "")
            if content:
                print(f"  내용    :\n{content[:300]}")

