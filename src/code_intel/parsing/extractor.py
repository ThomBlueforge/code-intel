"""Symbol extraction driven by Tree-sitter queries.

Given a language and source bytes, produces a flat list of ``ParsedSymbol``
records with parent links resolved by lexical nesting. Grammar loading and
query compilation are cached per language. Extraction is defensive: an
unsupported language or a parse failure yields an empty list rather than
raising, so the deterministic pipeline never breaks on one bad file.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from tree_sitter import Node, Query, QueryCursor
from tree_sitter_language_pack import get_language, get_parser

from code_intel.parsing.queries import LANGUAGE_QUERIES

# Nesting inside one of these turns a bare "function" into a "method".
_METHOD_PARENTS: frozenset[str] = frozenset({"class", "interface", "struct", "trait"})
_MAX_SIGNATURE_CHARS = 200
_HASH_DIGEST_SIZE = 16


@dataclass(frozen=True)
class ParsedSymbol:
    """A symbol extracted from a single file, before storage-level fields."""

    id: str
    name: str
    type: str
    start_line: int
    end_line: int
    signature: str
    visibility: str
    parent_id: str | None
    code: str
    hash: str


@dataclass
class _Raw:
    """Mutable intermediate record used while resolving parents."""

    id: str
    name: str
    type: str
    start_byte: int
    end_byte: int
    start_line: int
    end_line: int
    code: str
    language: str


class SymbolExtractor:
    """Extracts symbols for supported languages; caches compiled queries."""

    def __init__(self) -> None:
        self._queries: dict[str, Query] = {}

    def supports(self, language: str) -> bool:
        return language in LANGUAGE_QUERIES

    def extract(self, language: str, source: bytes) -> list[ParsedSymbol]:
        spec = LANGUAGE_QUERIES.get(language)
        if spec is None:
            return []
        pack_name, _ = spec
        try:
            parser = get_parser(pack_name)
            root = parser.parse(source).root_node
            cursor = QueryCursor(self._query_for(language, pack_name))
            matches = cursor.matches(root)
        except Exception:
            # A grammar or query failure must not break ingestion.
            return []

        raws = self._collect(matches, language)
        return self._resolve_parents(raws)

    def _query_for(self, language: str, pack_name: str) -> Query:
        cached = self._queries.get(language)
        if cached is None:
            _, query_src = LANGUAGE_QUERIES[language]
            cached = Query(get_language(pack_name), query_src)
            self._queries[language] = cached
        return cached

    def _collect(
        self, matches: list[tuple[int, dict[str, list[Node]]]], language: str
    ) -> list[_Raw]:
        seen: dict[tuple[int, int, str], _Raw] = {}
        for _pattern, caps in matches:
            kind = _kind_of(caps)
            name_nodes = caps.get("name")
            if kind is None or not name_nodes:
                continue
            def_nodes = caps[f"kind.{kind}"]
            def_node = def_nodes[0]
            name = _node_text(name_nodes[0])
            key = (def_node.start_byte, def_node.end_byte, kind)
            if key in seen:
                continue
            code = _node_text(def_node)
            seen[key] = _Raw(
                id=str(uuid.uuid4()),
                name=name,
                type=kind,
                start_byte=def_node.start_byte,
                end_byte=def_node.end_byte,
                start_line=def_node.start_point[0] + 1,
                end_line=def_node.end_point[0] + 1,
                code=code,
                language=language,
            )
        return list(seen.values())

    def _resolve_parents(self, raws: list[_Raw]) -> list[ParsedSymbol]:
        # Outer symbols first so containment scans are stable.
        ordered = sorted(raws, key=lambda r: (r.start_byte, -r.end_byte))
        result: list[ParsedSymbol] = []
        for child in ordered:
            parent = _nearest_enclosing(child, ordered)
            symbol_type = child.type
            if symbol_type == "global":
                # Keep only module-level assignments; drop class attrs / locals.
                if parent is not None:
                    continue
                if child.name.isupper():
                    symbol_type = "const"
            elif (
                symbol_type == "function"
                and parent is not None
                and parent.type in _METHOD_PARENTS
            ):
                symbol_type = "method"
            signature = _signature(child.code)
            result.append(
                ParsedSymbol(
                    id=child.id,
                    name=child.name,
                    type=symbol_type,
                    start_line=child.start_line,
                    end_line=child.end_line,
                    signature=signature,
                    visibility=_visibility(child.language, child.name, signature),
                    parent_id=parent.id if parent is not None else None,
                    code=child.code,
                    hash=_hash_code(child.code),
                )
            )
        return result


def _node_text(node: Node) -> str:
    return (node.text or b"").decode("utf-8", errors="replace")


def _kind_of(caps: dict[str, list[Node]]) -> str | None:
    for key in caps:
        if key.startswith("kind."):
            return key.split(".", 1)[1]
    return None


def _nearest_enclosing(child: _Raw, ordered: list[_Raw]) -> _Raw | None:
    best: _Raw | None = None
    for candidate in ordered:
        if candidate.id == child.id:
            continue
        encloses = (
            candidate.start_byte <= child.start_byte
            and candidate.end_byte >= child.end_byte
            and (candidate.start_byte, candidate.end_byte) != (child.start_byte, child.end_byte)
        )
        if not encloses:
            continue
        if best is None or candidate.start_byte > best.start_byte:
            best = candidate
    return best


def _signature(code: str) -> str:
    for line in code.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:_MAX_SIGNATURE_CHARS]
    return ""


def _visibility(language: str, name: str, signature: str) -> str:
    prefix = signature.split(name, 1)[0]
    for keyword in ("private", "protected", "public", "internal"):
        if keyword in prefix:
            return keyword
    if language == "Python":
        if name.startswith("__") and name.endswith("__"):
            return "public"
        return "private" if name.startswith("_") else "public"
    if language == "Go":
        return "public" if name[:1].isupper() else "private"
    if language == "Rust":
        return "public" if signature.lstrip().startswith("pub") else "private"
    return "unknown"


def _hash_code(code: str) -> str:
    return hashlib.blake2b(code.encode("utf-8"), digest_size=_HASH_DIGEST_SIZE).hexdigest()
