from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ParsedSymbol:
    symbol_type: str   # "function" | "class" | "struct" | "namespace" | "method" | "interface"
    symbol_name: str
    parent_class: str
    namespace: str
    start_line: int
    end_line: int
    content: str


def parse_file(file_path: str) -> list[ParsedSymbol]:
    """파일을 파싱하여 심볼 목록 반환. 실패 시 빈 리스트."""
    suffix = Path(file_path).suffix.lower()
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
    except OSError:
        return []

    if suffix in (".cpp", ".c", ".h", ".hpp", ".hxx", ".cxx"):
        return _parse_cpp(source, file_path)
    elif suffix == ".cs":
        return _parse_cs(source, file_path)
    return []


# ── C / C++ ──────────────────────────────────────────────────────────────────

def _parse_cpp(source: str, file_path: str) -> list[ParsedSymbol]:
    try:
        import tree_sitter_cpp as tscpp
        from tree_sitter import Language, Parser
        lang = Language(tscpp.language())
        parser = Parser(lang)
    except Exception:
        return []

    tree = parser.parse(source.encode("utf-8", errors="replace"))
    lines = source.splitlines()
    symbols: list[ParsedSymbol] = []
    _walk_cpp(tree.root_node, lines, symbols, namespace="", parent_class="")
    return symbols


def _walk_cpp(node, lines: list, symbols: list, namespace: str, parent_class: str):
    if node.type == "namespace_definition":
        name = _cpp_child_text(node, "namespace_identifier", lines)
        ns = f"{namespace}::{name}" if namespace else name
        for child in node.children:
            _walk_cpp(child, lines, symbols, namespace=ns, parent_class=parent_class)
        return

    if node.type in ("class_specifier", "struct_specifier"):
        name = _cpp_child_text(node, "type_identifier", lines)
        sym_type = "class" if node.type == "class_specifier" else "struct"
        start = node.start_point[0]
        end = node.end_point[0]
        symbols.append(ParsedSymbol(
            symbol_type=sym_type,
            symbol_name=f"{namespace}::{name}" if namespace else name,
            parent_class=parent_class,
            namespace=namespace,
            start_line=start + 1,
            end_line=end + 1,
            content="\n".join(lines[start:end + 1]),
        ))
        for child in node.children:
            _walk_cpp(child, lines, symbols, namespace=namespace, parent_class=name)
        return

    if node.type == "function_definition":
        name = _extract_cpp_func_name(node, lines)
        start = node.start_point[0]
        end = node.end_point[0]
        # "Class::Method" 처럼 한정자가 있으면 클래스 멤버 구현으로 판단
        raw_parent = parent_class
        if not raw_parent and "::" in name:
            parts = name.rsplit("::", 1)
            raw_parent = parts[0].split("::")[-1]
        full_name = f"{parent_class}::{name}" if parent_class else name
        if namespace:
            full_name = f"{namespace}::{full_name}"
        symbols.append(ParsedSymbol(
            symbol_type="method" if raw_parent else "function",
            symbol_name=full_name,
            parent_class=raw_parent,
            namespace=namespace,
            start_line=start + 1,
            end_line=end + 1,
            content="\n".join(lines[start:end + 1]),
        ))
        return

    # 헤더 파일의 메서드/함수 선언 (function_definition 이 아닌 declaration 노드)
    if node.type in ("declaration", "field_declaration"):
        decl_node = _find_function_declarator(node)
        if decl_node:
            name = _extract_cpp_func_name(decl_node, lines)
            start = node.start_point[0]
            end = node.end_point[0]
            full_name = f"{parent_class}::{name}" if parent_class else name
            if namespace:
                full_name = f"{namespace}::{full_name}"
            symbols.append(ParsedSymbol(
                symbol_type="method" if parent_class else "function",
                symbol_name=full_name,
                parent_class=parent_class,
                namespace=namespace,
                start_line=start + 1,
                end_line=end + 1,
                content="\n".join(lines[start:end + 1]),
            ))
            return

    for child in node.children:
        _walk_cpp(child, lines, symbols, namespace=namespace, parent_class=parent_class)


def _cpp_child_text(node, child_type: str, lines: list) -> str:
    for child in node.children:
        if child.type == child_type:
            s, e = child.start_point[0], child.end_point[0]
            return lines[s][child.start_point[1]:child.end_point[1]] if s == e else lines[s]
    return "unknown"


def _find_function_declarator(node):
    """declaration 서브트리에서 function_declarator 노드를 반환."""
    if node.type == "function_declarator":
        return node
    for child in node.children:
        found = _find_function_declarator(child)
        if found:
            return found
    return None


def _extract_cpp_func_name(node, lines: list) -> str:
    for child in node.children:
        if child.type in ("function_declarator", "pointer_declarator", "reference_declarator"):
            return _extract_cpp_func_name(child, lines)
        if child.type in ("qualified_identifier", "identifier", "field_identifier"):
            s, e = child.start_point[0], child.end_point[0]
            return lines[s][child.start_point[1]:child.end_point[1]] if s == e else lines[s]
        if child.type == "destructor_name":
            # ~ClassName 형태: 내부 identifier 추출
            for gc in child.children:
                if gc.type == "identifier":
                    s, e = gc.start_point[0], gc.end_point[0]
                    name = lines[s][gc.start_point[1]:gc.end_point[1]] if s == e else lines[s]
                    return f"~{name}"
    return "unknown"


# ── C# ───────────────────────────────────────────────────────────────────────

def _parse_cs(source: str, file_path: str) -> list[ParsedSymbol]:
    try:
        import tree_sitter_c_sharp as tscs
        from tree_sitter import Language, Parser
        lang = Language(tscs.language())
        parser = Parser(lang)
    except Exception:
        return []

    tree = parser.parse(source.encode("utf-8", errors="replace"))
    lines = source.splitlines()
    symbols: list[ParsedSymbol] = []
    _walk_cs(tree.root_node, lines, symbols, namespace="", parent_class="")
    return symbols


def _walk_cs(node, lines: list, symbols: list, namespace: str, parent_class: str):
    if node.type == "namespace_declaration":
        name_node = node.child_by_field_name("name")
        name = _node_text(name_node, lines) if name_node else ""
        ns = f"{namespace}.{name}" if namespace else name
        for child in node.children:
            _walk_cs(child, lines, symbols, namespace=ns, parent_class=parent_class)
        return

    if node.type in ("class_declaration", "interface_declaration", "struct_declaration", "record_declaration"):
        name_node = node.child_by_field_name("name")
        name = _node_text(name_node, lines) if name_node else "unknown"
        sym_type = {
            "class_declaration": "class",
            "interface_declaration": "interface",
            "struct_declaration": "struct",
            "record_declaration": "class",
        }.get(node.type, "class")
        start = node.start_point[0]
        end = node.end_point[0]
        full_name = f"{namespace}.{name}" if namespace else name
        symbols.append(ParsedSymbol(
            symbol_type=sym_type,
            symbol_name=full_name,
            parent_class=parent_class,
            namespace=namespace,
            start_line=start + 1,
            end_line=end + 1,
            content="\n".join(lines[start:end + 1]),
        ))
        for child in node.children:
            _walk_cs(child, lines, symbols, namespace=namespace, parent_class=name)
        return

    if node.type in ("method_declaration", "constructor_declaration"):
        name_node = node.child_by_field_name("name")
        name = _node_text(name_node, lines) if name_node else "unknown"
        start = node.start_point[0]
        end = node.end_point[0]
        full_name = f"{parent_class}.{name}" if parent_class else name
        if namespace:
            full_name = f"{namespace}.{full_name}"
        symbols.append(ParsedSymbol(
            symbol_type="method",
            symbol_name=full_name,
            parent_class=parent_class,
            namespace=namespace,
            start_line=start + 1,
            end_line=end + 1,
            content="\n".join(lines[start:end + 1]),
        ))
        return

    for child in node.children:
        _walk_cs(child, lines, symbols, namespace=namespace, parent_class=parent_class)


def _node_text(node, lines: list) -> str:
    if node is None:
        return ""
    s, e = node.start_point[0], node.end_point[0]
    if s == e:
        return lines[s][node.start_point[1]:node.end_point[1]]
    return lines[s][node.start_point[1]:]
