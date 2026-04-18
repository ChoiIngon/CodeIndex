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


def make_chunk_id(file_path: str, start_line: int, end_line: int) -> str:
    key = f"{file_path}:{start_line}:{end_line}"
    return str(uuid.uuid5(_CHUNK_NS, key))


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]


def chunk_file(file_path: str, cfg: dict) -> list[Chunk]:
    """파일 하나를 청크 목록으로 변환."""
    min_lines = cfg.get("chunk_min_lines", 5)
    max_lines = cfg.get("chunk_max_lines", 150)
    overlap = cfg.get("chunk_overlap_lines", 10)
    lang = Path(file_path).suffix.lstrip(".").lower()

    symbols = parse_file(file_path)

    if symbols:
        return _chunk_from_symbols(file_path, lang, symbols, max_lines, overlap, min_lines)
    return _chunk_sliding_window(file_path, lang, max_lines, overlap, min_lines)


def _chunk_from_symbols(
    file_path: str,
    lang: str,
    symbols: list[ParsedSymbol],
    max_lines: int,
    overlap: int,
    min_lines: int,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for sym in symbols:
        lines = sym.content.splitlines()
        if len(lines) < min_lines:
            continue

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
            ))
        else:
            # 큰 심볼은 max_lines 단위로 분할
            sub_chunks = _split_lines(lines, max_lines, overlap)
            for i, sub_lines in enumerate(sub_chunks):
                start = sym.start_line + i * (max_lines - overlap)
                end = start + len(sub_lines) - 1
                text = prefix + "\n".join(sub_lines)
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
                ))
    return chunks


def _chunk_sliding_window(
    file_path: str,
    lang: str,
    max_lines: int,
    overlap: int,
    min_lines: int,
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
