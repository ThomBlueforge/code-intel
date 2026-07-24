"""Phase 23 — bottom-up codebase comprehension.

Builds a holistic understanding of the repository the way an agent would orient
itself: symbol understandings roll up into a per-file description with enumerated
responsibilities, which roll up into a repository overview (how the modules fit
together). Every level degrades to a deterministic aggregate when no LLM is
available, so comprehension always exists — richer with a model, still useful
without one. Understanding is stored separately from deterministic facts and is
fingerprinted by ``content_hash`` for incremental rebuilds.

This module owns the deterministic aggregate builders. The LLM passes layer on
top: they consume these same grounded structures as context rather than raw
source, keeping cost bounded and output grounded.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, replace

from code_intel.dependencies.callgraph import CallGraph, build_call_graph
from code_intel.llm.client import ChatClient, LLMError
from code_intel.models import (
    EnrichedSymbol,
    FileUnderstanding,
    RepoUnderstanding,
    Symbol,
    utc_now_iso,
)
from code_intel.storage.repositories import (
    EnrichedSymbolStore,
    FileUnderstandingStore,
    RepositoryStore,
    RepoUnderstandingStore,
    SymbolStore,
)
from code_intel.understanding.comprehension_prompts import (
    build_file_messages,
    build_repo_messages,
)

# Top-level logical units whose descriptions become a file's responsibilities.
_TOP_LEVEL_TYPES = frozenset(
    {"function", "class", "interface", "struct", "trait", "enum"}
)
_ENTRY_BASENAMES = frozenset(
    {"main.py", "__main__.py", "app.py", "cli.py", "index.ts", "index.tsx", "main.go"}
)
_MAX_COLLABORATORS = 8
_MAX_RESPONSIBILITIES = 12
_MAX_ENTRY_POINTS = 12
_MAX_KEY_MODULES = 10
_AGGREGATE_CONFIDENCE = 0.5


@dataclass(frozen=True)
class ComprehensionReport:
    files_built: int
    files_skipped: int
    repo_built: bool
    source: str  # "aggregate" | "llm"


class ComprehensionBuilder:
    """Builds and persists file- and repo-level understanding for a repository."""

    def __init__(self, conn: sqlite3.Connection, repository_id: str) -> None:
        self._conn = conn
        self._repo_id = repository_id

    def build(
        self,
        *,
        chat_client: ChatClient | None = None,
        model: str = "",
        force: bool = False,
    ) -> ComprehensionReport:
        """Bottom-up build. Uses the LLM when given, else deterministic aggregate.

        Every file/repo LLM call degrades to the grounded aggregate on failure,
        and rebuilds are incremental (by ``content_hash``) unless ``force``.
        """
        symbols = SymbolStore(self._conn).list_for_repository(self._repo_id)
        enriched = EnrichedSymbolStore(self._conn).map_for_repository(self._repo_id)
        by_path = _by_path(symbols)
        call_graph = build_call_graph(symbols)
        path_by_id = {s.id: s.path for s in symbols}

        fstore = FileUnderstandingStore(self._conn)
        existing = {} if force else fstore.hashes(self._repo_id)
        now = utc_now_iso()

        built = skipped = 0
        used_llm = False
        for path, group in by_path.items():
            content_hash = _hash(s.hash for s in group)
            if existing.get(path) == content_hash:
                skipped += 1
                continue
            aggregate = self._aggregate_file(
                path, group, enriched, call_graph, path_by_id, content_hash, now
            )
            understanding = aggregate
            if chat_client is not None:
                understanding = self._llm_file(aggregate, chat_client, model, now)
                used_llm = used_llm or understanding.source == "llm"
            fstore.upsert(understanding)
            built += 1

        all_files = fstore.map_for_repository(self._repo_id)
        repo_understanding = self._aggregate_repo(symbols, all_files, now)
        if chat_client is not None:
            repo_understanding = self._llm_repo(
                repo_understanding, all_files, chat_client, model, now
            )
            used_llm = used_llm or repo_understanding.source == "llm"
        RepoUnderstandingStore(self._conn).upsert(repo_understanding)
        self._conn.commit()
        return ComprehensionReport(built, skipped, True, "llm" if used_llm else "aggregate")

    # --- LLM passes (grounded in the aggregate structures) ---------------

    def _llm_file(
        self, aggregate: FileUnderstanding, client: ChatClient, model: str, now: str
    ) -> FileUnderstanding:
        messages = build_file_messages(
            aggregate.path, aggregate.responsibilities, aggregate.collaborators
        )
        try:
            data = _json_object(client.complete(messages))
        except (LLMError, ValueError):
            return aggregate
        responsibilities = _as_str_list(data.get("responsibilities"))
        return replace(
            aggregate,
            summary=_as_str(data.get("summary"), aggregate.summary),
            responsibilities=responsibilities or aggregate.responsibilities,
            key_exports=_as_str_list(data.get("key_exports")) or aggregate.key_exports,
            role=_as_str(data.get("role"), aggregate.role),
            source="llm",
            confidence=_clamp(_as_float(data.get("confidence"), aggregate.confidence)),
            model=model,
            updated_at=now,
        )

    def _llm_repo(
        self,
        aggregate: RepoUnderstanding,
        files: dict[str, FileUnderstanding],
        client: ChatClient,
        model: str,
        now: str,
    ) -> RepoUnderstanding:
        repo = RepositoryStore(self._conn).get_by_id(self._repo_id)
        name = repo.name if repo else self._repo_id
        listing = [
            (fu.path, fu.role, fu.summary) for fu in sorted(files.values(), key=lambda f: f.path)
        ]
        messages = build_repo_messages(name, listing, aggregate.entry_points)
        try:
            data = _json_object(client.complete(messages))
        except (LLMError, ValueError):
            return aggregate
        return replace(
            aggregate,
            summary=_as_str(data.get("summary"), aggregate.summary),
            architecture=_as_str_list(data.get("architecture")) or aggregate.architecture,
            source="llm",
            confidence=_clamp(_as_float(data.get("confidence"), aggregate.confidence)),
            model=model,
            updated_at=now,
        )

    # --- deterministic file understanding --------------------------------

    def _aggregate_file(
        self,
        path: str,
        symbols: list[Symbol],
        enriched: dict[str, EnrichedSymbol],
        call_graph: CallGraph,
        path_by_id: dict[str, str],
        content_hash: str,
        now: str,
    ) -> FileUnderstanding:
        top = [s for s in symbols if s.parent_id is None and s.type in _TOP_LEVEL_TYPES]
        focus = top or symbols
        responsibilities = [
            f"{s.type} {s.name}: {_describe(s, enriched.get(s.id))}"
            for s in sorted(focus, key=lambda s: s.start_line)[:_MAX_RESPONSIBILITIES]
        ]
        exports = [s.name for s in top if s.visibility == "public"]
        collaborators = _collaborators(symbols, call_graph, path_by_id, path)
        role = _role(path, symbols, enriched)
        return FileUnderstanding(
            repository_id=self._repo_id,
            path=path,
            summary=_aggregate_file_summary(path, symbols, collaborators),
            responsibilities=responsibilities,
            key_exports=exports,
            collaborators=collaborators,
            role=role,
            source="aggregate",
            confidence=_AGGREGATE_CONFIDENCE,
            content_hash=content_hash,
            model="",
            created_at=now,
            updated_at=now,
        )

    # --- deterministic repository overview -------------------------------

    def _aggregate_repo(
        self,
        symbols: list[Symbol],
        files: dict[str, FileUnderstanding],
        now: str,
    ) -> RepoUnderstanding:
        repo = RepositoryStore(self._conn).get_by_id(self._repo_id)
        name = repo.name if repo else self._repo_id
        languages = Counter(s.language for s in symbols)
        lang_desc = ", ".join(k for k, _ in languages.most_common(4))
        summary = (
            f"`{name}`: {len(files)} files, {len(symbols)} symbols across {lang_desc}. "
            "Built bottom-up from per-file understanding."
        )
        return RepoUnderstanding(
            repository_id=self._repo_id,
            summary=summary,
            architecture=_architecture(files),
            entry_points=_entry_points(symbols),
            key_modules=_key_modules(symbols),
            source="aggregate",
            confidence=_AGGREGATE_CONFIDENCE,
            content_hash=_hash(fu.content_hash for fu in files.values()),
            model="",
            created_at=now,
            updated_at=now,
        )


# --- helpers -------------------------------------------------------------


def _describe(symbol: Symbol, enriched: EnrichedSymbol | None) -> str:
    if enriched is not None and enriched.summary and enriched.summary != "Unknown":
        return enriched.summary
    return symbol.signature or symbol.name


def _aggregate_file_summary(
    path: str, symbols: list[Symbol], collaborators: list[str]
) -> str:
    kinds = Counter(s.type for s in symbols)
    kind_desc = ", ".join(f"{n} {k}" for k, n in kinds.most_common())
    collab = f" Collaborates with {len(collaborators)} module(s)." if collaborators else ""
    return f"`{path}` defines {len(symbols)} symbols ({kind_desc})." + collab


def _collaborators(
    symbols: list[Symbol],
    call_graph: CallGraph,
    path_by_id: dict[str, str],
    self_path: str,
) -> list[str]:
    others: set[str] = set()
    for sym in symbols:
        for callee in call_graph.out_edges.get(sym.id, ()):
            other = path_by_id.get(callee)
            if other is not None and other != self_path:
                others.add(other)
        for caller in call_graph.in_edges.get(sym.id, ()):
            other = path_by_id.get(caller)
            if other is not None and other != self_path:
                others.add(other)
    return sorted(others)[:_MAX_COLLABORATORS]


def _role(path: str, symbols: list[Symbol], enriched: dict[str, EnrichedSymbol]) -> str:
    layers = Counter(
        enriched[s.id].architecture_layer
        for s in symbols
        if s.id in enriched and enriched[s.id].architecture_layer not in ("", "Unknown")
    )
    if layers:
        return layers.most_common(1)[0][0]
    parent = os.path.dirname(path)
    return os.path.basename(parent) if parent else "root"


def _architecture(files: dict[str, FileUnderstanding]) -> list[str]:
    packages: dict[str, list[str]] = defaultdict(list)
    for path, fu in files.items():
        top = path.split("/", 1)[0] if "/" in path else "."
        packages[top].append(fu.role)
    lines = []
    for pkg, roles in sorted(packages.items()):
        role_desc = ", ".join(sorted({r for r in roles if r})[:4])
        lines.append(
            f"{pkg}/ — {len(roles)} module(s)" + (f" ({role_desc})" if role_desc else "")
        )
    return lines


def _entry_points(symbols: list[Symbol]) -> list[str]:
    points: set[str] = set()
    for symbol in symbols:
        if symbol.name == "main" and symbol.type in ("function", "method"):
            points.add(f"{symbol.path}:{symbol.start_line} {symbol.name}")
    for path in {s.path for s in symbols}:
        if os.path.basename(path) in _ENTRY_BASENAMES:
            points.add(path)
    return sorted(points)[:_MAX_ENTRY_POINTS]


def _key_modules(symbols: list[Symbol]) -> list[str]:
    counts = Counter(s.path for s in symbols)
    return [f"{path} ({n} symbols)" for path, n in counts.most_common(_MAX_KEY_MODULES)]


def _by_path(symbols: list[Symbol]) -> dict[str, list[Symbol]]:
    grouped: dict[str, list[Symbol]] = defaultdict(list)
    for symbol in symbols:
        grouped[symbol.path].append(symbol)
    return grouped


def _hash(parts: Iterable[object]) -> str:
    digest = hashlib.blake2b(digest_size=16)
    for part in sorted(str(p) for p in parts):
        digest.update(part.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _json_object(raw: str) -> dict[str, object]:
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in response")
    parsed = json.loads(raw[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("JSON root is not an object")
    return parsed


def _as_str(value: object, default: str) -> str:
    return value if isinstance(value, str) and value.strip() else default


def _as_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _as_float(value: object, default: float) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
