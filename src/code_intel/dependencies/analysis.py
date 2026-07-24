"""Dependency and health analysis.

Builds an approximate call graph (from stored symbol source) and a module
dependency graph (from imports re-read from disk), then derives a report. Call
resolution is name-based: a call to ``foo`` links to every symbol named ``foo``.
This over-links in the presence of name collisions and is documented as a
heuristic; findings that are heuristic are labelled in the report.
"""

from __future__ import annotations

import os
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx

from code_intel.dependencies.callgraph import build_call_graph, in_degree_counter
from code_intel.dependencies.relationships import RelationshipExtractor
from code_intel.models import FileRecord, Symbol
from code_intel.storage.repositories import FileStore, SymbolStore

_CALLABLE_TYPES = frozenset({"function", "method"})
_ENTRY_NAMES = frozenset({"main"})
# Implicitly invoked and never called by name: a class constructor runs via
# ``new`` (JS/TS/Java/C#), so it is never dead even with no name-based callers.
_IMPLICIT_METHODS = frozenset({"constructor"})
_MIN_DUPLICATE_SPAN = 4  # lines; only flag non-trivial identical bodies
_TOP_N = 10

# Decorators that do NOT imply external invocation. Any other decorator
# (``@property``, ``@app.command``, ``@router.get``, ``@pytest.fixture``, …)
# means the symbol is called by a framework/attribute access that name-based
# resolution can't see, so it must not be reported as dead code.
_INERT_DECORATORS = frozenset({"staticmethod", "classmethod"})

# Hotspot resolution guards. Call edges are resolved by name (see callgraph.py),
# so a call to ``get`` links to every symbol named ``get``. For names shared by
# many symbols (``get``/``set``/``map``/…) that resolution is ambiguous and the
# inbound count is a collision artifact, not a real shared-utility signal.
_HOTSPOT_MIN_NAME_LEN = 3  # skip 1-2 char names (``t``/``e`` from minified code)
_HOTSPOT_MAX_HOMONYMS = 3  # skip names shared by more than this many symbols

_PY_CANDIDATES = ("{mod}.py", "{mod}/__init__.py")
_JS_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")


@dataclass(frozen=True)
class DuplicateGroup:
    count: int
    names: list[str]
    paths: list[str]


@dataclass(frozen=True)
class DependencyReport:
    files: int
    symbols: int
    languages: dict[str, int]
    call_edges: int
    import_edges: int
    duplicate_implementations: list[DuplicateGroup]
    circular_dependencies: list[list[str]]
    dead_code_candidates: list[str]  # "path:line name" (heuristic)
    orphan_modules: list[str]  # (heuristic)
    entry_points: list[str]  # "path name" (heuristic)
    shared_utilities: list[tuple[str, int]]  # (name, inbound calls) (heuristic)
    most_depended_modules: list[tuple[str, int]]  # (path, inbound imports)
    warnings: list[str] = field(default_factory=list)


class DependencyAnalyzer:
    """Computes a :class:`DependencyReport` for a repository."""

    def __init__(self, conn: sqlite3.Connection, repo_path: Path) -> None:
        self._conn = conn
        self._repo_path = repo_path
        self._rel = RelationshipExtractor()

    def analyze(self, repository_id: str) -> DependencyReport:
        symbols = SymbolStore(self._conn).list_for_repository(repository_id)
        files = FileStore(self._conn).list_records(repository_id)

        call_graph = build_call_graph(symbols)
        call_in = in_degree_counter(call_graph)
        module_graph, import_in, import_edges = self._module_graph(files)
        reference_counts = self._reference_counts(files)

        return DependencyReport(
            files=len(files),
            symbols=len(symbols),
            languages=self._language_breakdown(repository_id),
            call_edges=call_graph.edge_count,
            import_edges=import_edges,
            duplicate_implementations=self._duplicates(repository_id),
            circular_dependencies=_cycles(module_graph),
            dead_code_candidates=_dead_code(symbols, call_in, reference_counts),
            orphan_modules=_orphans(files, module_graph, symbols),
            entry_points=_entry_points(symbols),
            shared_utilities=_shared_utilities(symbols, call_in),
            most_depended_modules=import_in.most_common(_TOP_N),
        )

    # --- module graph ----------------------------------------------------

    def _module_graph(
        self, files: list[FileRecord]
    ) -> tuple[nx.DiGraph, Counter[str], int]:
        path_set = {f.path for f in files}
        graph: nx.DiGraph = nx.DiGraph()
        for file in files:
            graph.add_node(file.path)

        import_in: Counter[str] = Counter()
        edges = 0
        for file in files:
            if not self._rel.supports_imports(file.language):
                continue
            source = self._read(file.path)
            if source is None:
                continue
            for module in self._rel.extract_imports(file.language, source):
                target = _resolve_import(file.path, file.language, module, path_set)
                if target is not None and target != file.path and not graph.has_edge(
                    file.path, target
                ):
                    graph.add_edge(file.path, target)
                    import_in[target] += 1
                    edges += 1
        return graph, import_in, edges

    def _read(self, rel_path: str) -> bytes | None:
        try:
            return (self._repo_path / rel_path).read_bytes()
        except OSError:
            return None

    def _reference_counts(self, files: list[FileRecord]) -> Counter[str]:
        """Repo-wide count of every identifier occurrence, for dead-code liveness."""
        counts: Counter[str] = Counter()
        for file in files:
            if not self._rel.supports_references(file.language):
                continue
            source = self._read(file.path)
            if source is not None:
                counts.update(self._rel.extract_reference_names(file.language, source))
        return counts

    def _language_breakdown(self, repository_id: str) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT language, COUNT(*) AS n FROM files WHERE repository_id = ? "
            "GROUP BY language ORDER BY n DESC",
            (repository_id,),
        ).fetchall()
        return {row["language"]: row["n"] for row in rows}

    def _duplicates(self, repository_id: str) -> list[DuplicateGroup]:
        rows = self._conn.execute(
            "SELECT COUNT(*) AS c, GROUP_CONCAT(name) AS names, GROUP_CONCAT(path) AS paths "
            "FROM symbols WHERE repository_id = ? AND type IN ('function', 'method') "
            "AND (end_line - start_line) >= ? "
            "GROUP BY hash HAVING c > 1 ORDER BY c DESC LIMIT ?",
            (repository_id, _MIN_DUPLICATE_SPAN, _TOP_N),
        ).fetchall()
        return [
            DuplicateGroup(
                count=row["c"],
                names=sorted(set((row["names"] or "").split(","))),
                paths=sorted(set((row["paths"] or "").split(","))),
            )
            for row in rows
        ]


def _resolve_import(
    importer: str, language: str, module: str, path_set: set[str]
) -> str | None:
    if language == "Python":
        rel = module.replace(".", "/")
        for template in _PY_CANDIDATES:
            candidate = template.format(mod=rel)
            if candidate in path_set:
                return candidate
        return None
    if language in ("JavaScript", "TypeScript"):
        if not module.startswith("."):
            return None  # bare/external import
        base = os.path.normpath(os.path.join(os.path.dirname(importer), module))
        candidates = [f"{base}{ext}" for ext in _JS_EXTS]
        candidates += [f"{base}/index{ext}" for ext in _JS_EXTS]
        for candidate in candidates:
            if candidate in path_set:
                return candidate
        return None
    return None


def _cycles(graph: nx.DiGraph) -> list[list[str]]:
    cycles: list[list[str]] = []
    for cycle in nx.simple_cycles(graph):
        cycles.append(cycle)
        if len(cycles) >= _TOP_N:
            break
    return cycles


def _dead_code(
    symbols: list[Symbol], call_in: Counter[str], reference_counts: Counter[str]
) -> list[str]:
    # A name appears once per definition site in the identifier scan; anything
    # beyond that is a use (JSX element, prop, member access, export, module
    # -level call) that name-based call resolution can't see.
    def_counts: Counter[str] = Counter(sym.name for sym in symbols)
    candidates: list[str] = []
    for sym in symbols:
        if sym.type not in _CALLABLE_TYPES:
            continue
        if call_in.get(sym.id, 0) > 0:
            continue
        if sym.name in _ENTRY_NAMES or sym.name in _IMPLICIT_METHODS:
            continue
        if sym.name.startswith("test"):
            continue
        if sym.name.startswith("__") and sym.name.endswith("__"):
            continue  # dunder methods are called implicitly
        if any(d not in _INERT_DECORATORS for d in sym.decorators):
            continue  # decorated -> invoked by a framework / accessed as a property
        if reference_counts.get(sym.name, 0) > def_counts.get(sym.name, 0):
            continue  # referenced by name somewhere beyond its definition(s)
        candidates.append(f"{sym.path}:{sym.start_line} {sym.name}")
    return sorted(candidates)


def _orphans(
    files: list[FileRecord], graph: nx.DiGraph, symbols: list[Symbol]
) -> list[str]:
    entry_paths = {ep.split(" ", 1)[0].rsplit(":", 1)[0] for ep in _entry_points(symbols)}
    return sorted(
        f.path
        for f in files
        if f.path in graph and graph.in_degree(f.path) == 0 and f.path not in entry_paths
    )


def _entry_points(symbols: list[Symbol]) -> list[str]:
    return sorted(
        f"{sym.path}:{sym.start_line} {sym.name}"
        for sym in symbols
        if sym.name in _ENTRY_NAMES and sym.type in _CALLABLE_TYPES
    )


def _shared_utilities(symbols: list[Symbol], call_in: Counter[str]) -> list[tuple[str, int]]:
    name_by_id = {s.id: s.name for s in symbols}
    homonyms: Counter[str] = Counter(s.name for s in symbols)

    # Collapse to one row per name (the same short name resolves to many symbol
    # ids, each carrying a near-identical inflated count), dropping names that
    # name-based resolution can't attribute confidently.
    best_by_name: dict[str, int] = {}
    for symbol_id, count in call_in.items():
        if count <= 1:
            continue
        name = name_by_id.get(symbol_id)
        if name is None or len(name) < _HOTSPOT_MIN_NAME_LEN:
            continue
        if homonyms[name] > _HOTSPOT_MAX_HOMONYMS:
            continue  # ambiguous callee: count is a name-collision artifact
        if count > best_by_name.get(name, 0):
            best_by_name[name] = count

    return sorted(best_by_name.items(), key=lambda item: (-item[1], item[0]))[:_TOP_N]
