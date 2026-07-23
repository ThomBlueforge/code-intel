"""Call and import relationship extraction.

Two Tree-sitter query families per supported language: callee names inside a
code unit, and imported module strings in a file. Queries are compiled once and
cached. Languages without queries yield empty lists (the analyzer still runs).
Validated against real grammar output before committing.
"""

from __future__ import annotations

from tree_sitter import Node, Query, QueryCursor
from tree_sitter_language_pack import get_language, get_parser

# canonical language -> (pack grammar name, call query)
_CALL_QUERIES: dict[str, tuple[str, str]] = {
    "Python": (
        "python",
        r"""
        (call function: (identifier) @callee)
        (call function: (attribute attribute: (identifier) @callee))
        """,
    ),
    "JavaScript": (
        "javascript",
        r"""
        (call_expression function: (identifier) @callee)
        (call_expression function: (member_expression property: (property_identifier) @callee))
        """,
    ),
    "TypeScript": (
        "typescript",
        r"""
        (call_expression function: (identifier) @callee)
        (call_expression function: (member_expression property: (property_identifier) @callee))
        """,
    ),
    "Go": (
        "go",
        r"""
        (call_expression function: (identifier) @callee)
        (call_expression function: (selector_expression field: (field_identifier) @callee))
        """,
    ),
}

# canonical language -> (pack grammar name, import query)
_IMPORT_QUERIES: dict[str, tuple[str, str]] = {
    "Python": (
        "python",
        r"""
        (import_statement name: (dotted_name) @mod)
        (import_from_statement module_name: (dotted_name) @mod)
        """,
    ),
    "JavaScript": (
        "javascript",
        r"""
        (import_statement source: (string (string_fragment) @mod))
        """,
    ),
    "TypeScript": (
        "typescript",
        r"""
        (import_statement source: (string (string_fragment) @mod))
        """,
    ),
    "Go": (
        "go",
        r"""
        (import_spec path: (interpreted_string_literal) @mod)
        """,
    ),
}


class RelationshipExtractor:
    """Extracts callee names and import module strings; caches queries."""

    def __init__(self) -> None:
        self._compiled: dict[str, Query] = {}

    def supports_calls(self, language: str) -> bool:
        return language in _CALL_QUERIES

    def supports_imports(self, language: str) -> bool:
        return language in _IMPORT_QUERIES

    def extract_call_names(self, language: str, source: bytes) -> list[str]:
        spec = _CALL_QUERIES.get(language)
        if spec is None:
            return []
        return self._run(f"call:{language}", spec, source, "callee")

    def extract_imports(self, language: str, source: bytes) -> list[str]:
        spec = _IMPORT_QUERIES.get(language)
        if spec is None:
            return []
        return [_strip_quotes(m) for m in self._run(f"imp:{language}", spec, source, "mod")]

    def _run(
        self, cache_key: str, spec: tuple[str, str], source: bytes, capture: str
    ) -> list[str]:
        pack_name, query_src = spec
        try:
            query = self._compiled.get(cache_key)
            if query is None:
                query = Query(get_language(pack_name), query_src)
                self._compiled[cache_key] = query
            root = get_parser(pack_name).parse(source).root_node
            matches = QueryCursor(query).matches(root)
        except Exception:
            return []
        names: list[str] = []
        for _pattern, caps in matches:
            for node in caps.get(capture, []):
                names.append(_node_text(node))
        return names


def _node_text(node: Node) -> str:
    return (node.text or b"").decode("utf-8", errors="replace")


def _strip_quotes(value: str) -> str:
    return value.strip().strip("\"'`")
