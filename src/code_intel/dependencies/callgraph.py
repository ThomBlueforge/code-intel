"""Reusable approximate call graph.

Built from stored symbol source using name-based callee resolution (a call to
``foo`` links to every symbol named ``foo``). Shared by dependency analysis
(Phase 5), change-impact analysis (Phase 22), and intelligence (Phase 13) so the
approximation lives in exactly one place. Name-based resolution is a documented
heuristic, not proof of a call.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from code_intel.dependencies.relationships import RelationshipExtractor
from code_intel.models import Symbol


@dataclass(frozen=True)
class CallGraph:
    """Directed call relationships between symbols (by id)."""

    out_edges: dict[str, set[str]]  # caller id -> callee ids
    in_edges: dict[str, set[str]]  # callee id -> caller ids
    symbols: dict[str, Symbol] = field(default_factory=dict)

    def in_count(self, symbol_id: str) -> int:
        return len(self.in_edges.get(symbol_id, ()))

    @property
    def edge_count(self) -> int:
        return sum(len(v) for v in self.out_edges.values())


def build_call_graph(symbols: list[Symbol]) -> CallGraph:
    extractor = RelationshipExtractor()
    by_name: dict[str, list[str]] = defaultdict(list)
    for symbol in symbols:
        by_name[symbol.name].append(symbol.id)

    out_edges: dict[str, set[str]] = defaultdict(set)
    in_edges: dict[str, set[str]] = defaultdict(set)
    for symbol in symbols:
        if not extractor.supports_calls(symbol.language):
            continue
        for callee in extractor.extract_call_names(symbol.language, symbol.code.encode("utf-8")):
            for target_id in by_name.get(callee, ()):
                if target_id != symbol.id:
                    out_edges[symbol.id].add(target_id)
                    in_edges[target_id].add(symbol.id)

    return CallGraph(
        out_edges=dict(out_edges),
        in_edges=dict(in_edges),
        symbols={s.id: s for s in symbols},
    )


def in_degree_counter(call_graph: CallGraph) -> Counter[str]:
    """Inbound call counts per symbol id."""
    return Counter({sid: len(callers) for sid, callers in call_graph.in_edges.items()})
