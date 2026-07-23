"""Phase 11 — hierarchical summaries (repository memory).

Builds summaries bottom-up: symbol → module (file) → package (directory) →
repository. Symbol summaries reuse AI enrichment when present and fall back to a
deterministic description otherwise, so this works with the LLM disabled.
Summaries are persisted separately from embeddings in the ``summaries`` table.
"""

from __future__ import annotations

import os
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass

from code_intel.models import Summary, Symbol, utc_now_iso
from code_intel.storage.repositories import RepositoryStore, SummaryStore, SymbolStore

_SYMBOL_SCOPES = frozenset(
    {"function", "method", "class", "interface", "struct", "trait", "enum"}
)


@dataclass(frozen=True)
class Explanation:
    """A summary at a requested granularity."""

    scope: str
    target: str
    summary: str
    details: list[str]


class SummaryBuilder:
    """Produces and persists hierarchical summaries; answers ``explain``."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def build_repository(self, repository_id: str) -> int:
        """Build and persist every summary level. Returns the count written."""
        symbols = SymbolStore(self._conn).list_for_repository(repository_id)
        enriched = self._enriched_summaries()
        store = SummaryStore(self._conn)
        now = utc_now_iso()
        written = 0

        for symbol in symbols:
            store.upsert(
                Summary(
                    scope=symbol.type,
                    target_key=symbol.id,
                    path=symbol.path,
                    summary=_symbol_summary(symbol, enriched.get(symbol.id)),
                    source="llm" if symbol.id in enriched else "aggregate",
                    confidence=0.9 if symbol.id in enriched else 0.6,
                    created_at=now,
                )
            )
            written += 1

        for path, group in _by_path(symbols).items():
            store.upsert(
                Summary(
                    scope="module",
                    target_key=path,
                    path=path,
                    summary=_module_summary(path, group, enriched),
                    source="aggregate",
                    confidence=0.7,
                    created_at=now,
                )
            )
            written += 1

        for package, paths in _packages(symbols).items():
            store.upsert(
                Summary(
                    scope="package",
                    target_key=package,
                    path=package,
                    summary=f"Package `{package}` spans {len(paths)} module(s).",
                    source="aggregate",
                    confidence=0.6,
                    created_at=now,
                )
            )
            written += 1

        repo = RepositoryStore(self._conn).get_by_id(repository_id)
        repo_name = repo.name if repo else repository_id
        store.upsert(
            Summary(
                scope="repository",
                target_key=repository_id,
                path=".",
                summary=_repository_summary(repo_name, symbols, enriched),
                source="aggregate",
                confidence=0.6,
                created_at=now,
            )
        )
        written += 1
        self._conn.commit()
        return written

    def explain(self, repository_id: str, target: str) -> Explanation | None:
        """Return a summary appropriate to the granularity of ``target``."""
        symbols = SymbolStore(self._conn).list_for_repository(repository_id)
        enriched = self._enriched_summaries()
        by_path = _by_path(symbols)

        normalized = target.strip("/").replace("./", "")
        repo = RepositoryStore(self._conn).get_by_id(repository_id)
        if target in (".", "", "/") or (repo is not None and target == repo.path):
            name = repo.name if repo else repository_id
            return Explanation(
                scope="repository",
                target=name,
                summary=_repository_summary(name, symbols, enriched),
                details=_repository_details(symbols, enriched),
            )
        if normalized in by_path:
            group = by_path[normalized]
            return Explanation(
                scope="module",
                target=normalized,
                summary=_module_summary(normalized, group, enriched),
                details=[f"{s.type} {s.name} (line {s.start_line})" for s in group],
            )
        package_paths = [p for p in by_path if p.startswith(normalized + "/")]
        if package_paths:
            return Explanation(
                scope="package",
                target=normalized,
                summary=f"Package `{normalized}` spans {len(package_paths)} module(s).",
                details=sorted(package_paths),
            )
        for symbol in symbols:
            if symbol.name == normalized or symbol.name == target:
                return Explanation(
                    scope=symbol.type,
                    target=symbol.name,
                    summary=_symbol_summary(symbol, enriched.get(symbol.id)),
                    details=[f"{symbol.path}:{symbol.start_line}-{symbol.end_line}"],
                )
        return None

    def _enriched_summaries(self) -> dict[str, str]:
        rows = self._conn.execute(
            "SELECT symbol_id, summary FROM enriched_symbols WHERE summary != 'Unknown'"
        ).fetchall()
        return {row["symbol_id"]: row["summary"] for row in rows}


def _symbol_summary(symbol: Symbol, enriched_summary: str | None) -> str:
    if enriched_summary:
        return enriched_summary
    return f"{symbol.type} `{symbol.name}` — {symbol.signature}"


def _module_summary(path: str, symbols: list[Symbol], enriched: dict[str, str]) -> str:
    kinds = Counter(s.type for s in symbols)
    kind_desc = ", ".join(f"{n} {k}" for k, n in kinds.most_common())
    names = ", ".join(sorted({s.name for s in symbols})[:6])
    enriched_here = sum(1 for s in symbols if s.id in enriched)
    tail = f" ({enriched_here} AI-summarised)" if enriched_here else ""
    return f"Module `{path}` defines {len(symbols)} symbols — {kind_desc}. Key: {names}.{tail}"


def _repository_summary(name: str, symbols: list[Symbol], enriched: dict[str, str]) -> str:
    languages = Counter(s.language for s in symbols)
    lang_desc = ", ".join(f"{k}" for k, _ in languages.most_common(4))
    files = len({s.path for s in symbols})
    return (
        f"Repository `{name}`: {files} module(s), {len(symbols)} symbols "
        f"across {lang_desc}. {len(enriched)} symbols carry AI summaries."
    )


def _repository_details(symbols: list[Symbol], enriched: dict[str, str]) -> list[str]:
    kinds = Counter(s.type for s in symbols)
    return [f"{n} {k}" for k, n in kinds.most_common()]


def _by_path(symbols: list[Symbol]) -> dict[str, list[Symbol]]:
    grouped: dict[str, list[Symbol]] = defaultdict(list)
    for symbol in symbols:
        grouped[symbol.path].append(symbol)
    return grouped


def _packages(symbols: list[Symbol]) -> dict[str, list[str]]:
    packages: dict[str, set[str]] = defaultdict(set)
    for symbol in symbols:
        package = os.path.dirname(symbol.path) or "."
        packages[package].add(symbol.path)
    return {k: sorted(v) for k, v in packages.items()}
