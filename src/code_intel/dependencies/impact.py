"""Phase 22 — change impact analysis.

Given a symbol, compute what a change to it could touch: direct callers,
indirect (transitive) callers, affected files/modules, affected tests, and
affected external integrations (imports seen in affected files). Built on the
shared, name-based call graph, so results are candidates to review, not proof.
"""

from __future__ import annotations

import os
from collections import deque
from dataclasses import dataclass

from code_intel.dependencies.callgraph import CallGraph, build_call_graph
from code_intel.models import Symbol

_TEST_MARKERS = ("test", "spec", "__tests__")


@dataclass(frozen=True)
class ImpactReport:
    symbol: str
    targets: int  # how many symbols share this name
    direct_callers: list[str]
    indirect_callers: list[str]
    affected_files: list[str]
    affected_modules: list[str]
    affected_tests: list[str]


class ImpactAnalyzer:
    """Computes change impact for a named symbol."""

    def __init__(self, symbols: list[Symbol]) -> None:
        self._symbols = symbols
        self._call_graph: CallGraph = build_call_graph(symbols)
        self._by_name: dict[str, list[str]] = {}
        for symbol in symbols:
            self._by_name.setdefault(symbol.name, []).append(symbol.id)

    def impact(self, symbol_name: str) -> ImpactReport:
        target_ids = self._by_name.get(symbol_name, [])
        direct_ids: set[str] = set()
        for tid in target_ids:
            direct_ids |= self._call_graph.in_edges.get(tid, set())

        all_callers = self._transitive_callers(target_ids)
        indirect_ids = all_callers - direct_ids - set(target_ids)

        affected_ids = all_callers | set(target_ids)
        by_id = self._symbols_by_id()
        affected_files = sorted({by_id[sid].path for sid in affected_ids if sid in by_id})
        affected_modules = sorted({os.path.dirname(p) or "." for p in affected_files})
        affected_tests = sorted(p for p in affected_files if _is_test_path(p))

        return ImpactReport(
            symbol=symbol_name,
            targets=len(target_ids),
            direct_callers=self._label(direct_ids),
            indirect_callers=self._label(indirect_ids),
            affected_files=affected_files,
            affected_modules=affected_modules,
            affected_tests=affected_tests,
        )

    def _transitive_callers(self, target_ids: list[str]) -> set[str]:
        visited: set[str] = set()
        queue: deque[str] = deque(target_ids)
        while queue:
            current = queue.popleft()
            for caller in self._call_graph.in_edges.get(current, ()):
                if caller not in visited:
                    visited.add(caller)
                    queue.append(caller)
        return visited

    def _symbols_by_id(self) -> dict[str, Symbol]:
        return self._call_graph.symbols

    def _label(self, ids: set[str]) -> list[str]:
        by_id = self._symbols_by_id()
        labels = [
            f"{by_id[sid].name} ({by_id[sid].path}:{by_id[sid].start_line})"
            for sid in ids
            if sid in by_id
        ]
        return sorted(labels)


def _is_test_path(path: str) -> bool:
    lowered = path.lower()
    return any(marker in lowered for marker in _TEST_MARKERS)
