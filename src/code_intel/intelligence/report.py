"""Repository intelligence (Phases 13 & 21).

Aggregates deterministic analysis (dependency cycles, duplicates, dead code,
hotspots), class pattern detection, function-size smells, and — when enrichment
exists — domain/layer structure into a single set of `Finding`s. Structural
findings are `STATIC_ANALYSIS`; enrichment-derived ones are `LLM_INFERENCE`,
kept separable by `origin`. Findings are persisted so runs can be diffed.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from code_intel.dependencies.analysis import DependencyAnalyzer, DependencyReport
from code_intel.graph.interface import ORIGIN_LLM, ORIGIN_STATIC
from code_intel.intelligence.patterns import PatternDetector
from code_intel.models import Finding, Symbol, utc_now_iso
from code_intel.storage.repositories import SymbolStore

_LONG_FUNCTION_LOC = 60
_CALLABLE_TYPES = frozenset({"function", "method"})
_MIN_DOMAIN_COUNT = 2


@dataclass(frozen=True)
class IntelligenceReport:
    findings: list[Finding]

    @property
    def by_category(self) -> dict[str, int]:
        counts: Counter[str] = Counter(f.category for f in self.findings)
        return dict(counts.most_common())

    @property
    def by_origin(self) -> dict[str, int]:
        counts: Counter[str] = Counter(f.origin for f in self.findings)
        return dict(counts.most_common())


class IntelligenceEngine:
    """Computes repository intelligence findings."""

    def __init__(self, conn: sqlite3.Connection, repo_path: Path) -> None:
        self._conn = conn
        self._repo_path = repo_path

    def analyze(self, repository_id: str) -> IntelligenceReport:
        symbols = SymbolStore(self._conn).list_for_repository(repository_id)
        children = _children_by_parent(symbols)
        now = utc_now_iso()
        findings: list[Finding] = []

        dep = DependencyAnalyzer(self._conn, self._repo_path).analyze(repository_id)
        findings.extend(self._from_dependencies(repository_id, dep, now))
        findings.extend(self._from_patterns(repository_id, symbols, children, now))
        findings.extend(self._long_functions(repository_id, symbols, now))
        findings.extend(self._from_enrichment(repository_id, now))
        return IntelligenceReport(findings=findings)

    def _from_dependencies(
        self, repo_id: str, dep: DependencyReport, now: str
    ) -> list[Finding]:
        out: list[Finding] = []
        for cycle in dep.circular_dependencies:
            out.append(
                _finding(repo_id, "circular_dependency", "Circular dependency",
                         " → ".join(cycle), ORIGIN_STATIC, 0.9, cycle[0] if cycle else "", now)
            )
        for group in dep.duplicate_implementations:
            out.append(
                _finding(repo_id, "duplicate_logic", "Duplicate implementation",
                         f"{group.count}× identical: {', '.join(group.names)}",
                         ORIGIN_STATIC, 0.85, ", ".join(group.paths[:3]), now)
            )
        for candidate in dep.dead_code_candidates[:50]:
            out.append(
                _finding(repo_id, "dead_code", "Dead-code candidate", candidate,
                         ORIGIN_STATIC, 0.5, candidate, now)
            )
        for name, count in dep.shared_utilities:
            out.append(
                _finding(repo_id, "hotspot", "Shared utility (hotspot)",
                         f"{name} is called {count}×", ORIGIN_STATIC, 0.7, name, now)
            )
        return out

    def _from_patterns(
        self,
        repo_id: str,
        symbols: list[Symbol],
        children: dict[str, list[Symbol]],
        now: str,
    ) -> list[Finding]:
        return [
            _finding(
                repo_id, dp.category, dp.title, dp.detail, ORIGIN_STATIC, dp.confidence,
                dp.target, now,
            )
            for dp in PatternDetector().detect(symbols, children)
        ]

    def _long_functions(
        self, repo_id: str, symbols: list[Symbol], now: str
    ) -> list[Finding]:
        out: list[Finding] = []
        for symbol in symbols:
            if symbol.type not in _CALLABLE_TYPES:
                continue
            loc = symbol.end_line - symbol.start_line + 1
            if loc >= _LONG_FUNCTION_LOC:
                out.append(
                    _finding(
                        repo_id, "long_function", "Long function",
                        f"`{symbol.name}` spans {loc} lines at {symbol.path}:{symbol.start_line}",
                        ORIGIN_STATIC, 0.55, symbol.name, now,
                    )
                )
        return out

    def _from_enrichment(self, repo_id: str, now: str) -> list[Finding]:
        rows = self._conn.execute(
            "SELECT es.business_domain, es.architecture_layer FROM enriched_symbols es "
            "JOIN symbols s ON s.id = es.symbol_id WHERE s.repository_id = ?",
            (repo_id,),
        ).fetchall()
        if not rows:
            return []
        domains: Counter[str] = Counter()
        layers: Counter[str] = Counter()
        for row in rows:
            for domain in json.loads(row["business_domain"]):
                if domain != "Unknown":
                    domains[domain] += 1
            if row["architecture_layer"] not in ("", "Unknown"):
                layers[row["architecture_layer"]] += 1

        out: list[Finding] = []
        for domain, count in domains.items():
            if count >= _MIN_DOMAIN_COUNT:
                out.append(
                    _finding(repo_id, "business_domain", f"Domain: {domain}",
                             f"{count} symbols relate to {domain}", ORIGIN_LLM,
                             0.6, domain, now)
                )
        for layer, count in layers.items():
            out.append(
                _finding(repo_id, "architecture_layer", f"Layer: {layer}",
                         f"{count} symbols in the {layer} layer", ORIGIN_LLM, 0.6, layer, now)
            )
        return out


def _finding(
    repo_id: str,
    category: str,
    title: str,
    detail: str,
    origin: str,
    confidence: float,
    target: str,
    now: str,
) -> Finding:
    return Finding(
        id=str(uuid.uuid4()),
        repository_id=repo_id,
        category=category,
        title=title,
        detail=detail,
        origin=origin,
        confidence=confidence,
        target=target,
        created_at=now,
    )


def _children_by_parent(symbols: list[Symbol]) -> dict[str, list[Symbol]]:
    children: dict[str, list[Symbol]] = defaultdict(list)
    for symbol in symbols:
        if symbol.parent_id:
            children[symbol.parent_id].append(symbol)
    return children
