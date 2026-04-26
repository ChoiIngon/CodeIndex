from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path

from .parser import ParsedSymbol, parse_file

_CHUNK_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


@dataclass
class Chunk:
    chunk_id: str
    file_path: str
    language: str
    start_line: int
    end_line: int
    symbol_type: str
    symbol_name: str
    parent_class: str
    namespace: str
    content: str
    content_hash: str
    project_name: str = ""


def make_chunk_id(file_path: str, start_line: int, end_line: int) -> str:
    key = f"{file_path}:{start_line}:{end_line}"
    return str(uuid.uuid5(_CHUNK_NS, key))


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]


_EXT_LANG_MAP: dict[str, str] = {
    ".h":   "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
    ".cxx": "cpp",
    ".c":   "cpp",
}


def chunk_file(file_path: str, cfg: dict, project_name: str = "") -> list[Chunk]:
    """파일 하나를 청크 목록으로 변환."""
    min_lines = cfg.get("chunk_min_lines", 5)
    max_lines = cfg.get("chunk_max_lines", 150)
    overlap = cfg.get("chunk_overlap_lines", 10)
    suffix = Path(file_path).suffix.lower()
    lang = _EXT_LANG_MAP.get(suffix, suffix.lstrip("."))

    symbols = parse_file(file_path)

    if symbols:
        chunks = _chunk_from_symbols(file_path, lang, symbols, max_lines, overlap, min_lines, project_name)
        return _deduplicate_chunks(chunks)
    return _chunk_sliding_window(file_path, lang, max_lines, overlap, min_lines, project_name)


# 심볼 우선순위: 높을수록 구체적 (중복 제거 시 우선 유지)
_SYMBOL_PRIORITY = {
    "function": 0, "method": 0,       # 가장 구체적
    "struct": 1, "interface": 1,
    "class": 2, "namespace": 3,       # 가장 추상적
    "code": 4,
}


def _overlap_ratio(a_start: int, a_end: int, b_start: int, b_end: int) -> float:
    """두 라인 범위의 걸침 비율 (0~1). 작은 범위 기준."""
    lo = max(a_start, b_start)
    hi = min(a_end, b_end)
    if hi < lo:
        return 0.0
    overlap_lines = hi - lo + 1
    smaller = min(a_end - a_start + 1, b_end - b_start + 1)
    return overlap_lines / smaller if smaller > 0 else 0.0


def _deduplicate_chunks(chunks: list[Chunk]) -> list[Chunk]:
    """라인 범위가 80% 이상 겹치는 청크 짝 중 덜 구체적인 심볼 타입의 청크만 유지."""
    if not chunks:
        return chunks

    # 우선순위 오름온: 구체적 심볼 타입 먼저
    ordered = sorted(chunks, key=lambda c: _SYMBOL_PRIORITY.get(c.symbol_type, 4))
    kept: list[Chunk] = []

    for candidate in ordered:
        dominated = False
        for existing in kept:
            ratio = _overlap_ratio(
                candidate.start_line, candidate.end_line,
                existing.start_line, existing.end_line,
            )
            if ratio >= 0.8:
                # 클래스/구조체가 자신의 멤버(method)에 의해 제거되지 않도록 예외 처리
                if (existing.parent_class
                        and candidate.symbol_type in ("class", "struct", "interface")):
                    continue
                # 같은 우선순위면 둘 다 유지, 더 추상적이면 제거
                if (_SYMBOL_PRIORITY.get(candidate.symbol_type, 4)
                        > _SYMBOL_PRIORITY.get(existing.symbol_type, 4)):
                    dominated = True
                    break
        if not dominated:
            kept.append(candidate)
    return kept


def _chunk_from_symbols(
    file_path: str,
    lang: str,
    symbols: list[ParsedSymbol],
    max_lines: int,
    overlap: int,
    min_lines: int,
    project_name: str = "",
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for sym in symbols:
        lines = sym.content.splitlines()
        # 클래스 멤버(선언 포함)는 min_lines 필터 적용 안 함
        if len(lines) < min_lines and not sym.parent_class:
            continue

        # 헤더: class 컨텍스트 포함
        if sym.parent_class:
            prefix = f"// File: {file_path} | class: {sym.parent_class} | {sym.symbol_type}: {sym.symbol_name}\n"
        else:
            prefix = f"// File: {file_path} | {sym.symbol_type}: {sym.symbol_name}\n"

        if len(lines) <= max_lines:
            text = prefix + sym.content
            chunks.append(Chunk(
                chunk_id=make_chunk_id(file_path, sym.start_line, sym.end_line),
                file_path=file_path,
                language=lang,
                start_line=sym.start_line,
                end_line=sym.end_line,
                symbol_type=sym.symbol_type,
                symbol_name=sym.symbol_name,
                parent_class=sym.parent_class,
                namespace=sym.namespace,
                content=text,
                content_hash=content_hash(text),
                project_name=project_name,
            ))
        else:
            # 큰 심볼은 max_lines 단위로 분할 — 모든 청크에 (part N/M) 시그니처 유지
            sub_chunks = _split_lines(lines, max_lines, overlap)
            total_parts = len(sub_chunks)
            for i, sub_lines in enumerate(sub_chunks):
                start = sym.start_line + i * (max_lines - overlap)
                end = start + len(sub_lines) - 1
                part_prefix = prefix.rstrip("\n") + f" (part {i+1}/{total_parts})\n"
                text = part_prefix + "\n".join(sub_lines)
                chunks.append(Chunk(
                    chunk_id=make_chunk_id(file_path, start, end),
                    file_path=file_path,
                    language=lang,
                    start_line=start,
                    end_line=end,
                    symbol_type=sym.symbol_type,
                    symbol_name=sym.symbol_name,
                    parent_class=sym.parent_class,
                    namespace=sym.namespace,
                    content=text,
                    content_hash=content_hash(text),
                    project_name=project_name,
                ))
    return chunks


def _chunk_sliding_window(
    file_path: str,
    lang: str,
    max_lines: int,
    overlap: int,
    min_lines: int,
    project_name: str = "",
) -> list[Chunk]:
    """AST 파싱 실패 시 슬라이딩 윈도우 폴백."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
    except OSError:
        return []

    chunks: list[Chunk] = []
    step = max(1, max_lines - overlap)
    n = len(all_lines)

    for start in range(0, n, step):
        end = min(start + max_lines, n)
        sub = all_lines[start:end]
        if len(sub) < min_lines:
            break
        text = "".join(sub)
        chunks.append(Chunk(
            chunk_id=make_chunk_id(file_path, start + 1, end),
            file_path=file_path,
            language=lang,
            start_line=start + 1,
            end_line=end,
            symbol_type="code",
            symbol_name="",
            parent_class="",
            namespace="",
            content=text,
            content_hash=content_hash(text),
            project_name=project_name,
        ))
    return chunks


def _split_lines(lines: list, max_lines: int, overlap: int) -> list[list]:
    step = max(1, max_lines - overlap)
    result = []
    for i in range(0, len(lines), step):
        chunk = lines[i: i + max_lines]
        if chunk:
            result.append(chunk)
    return result
