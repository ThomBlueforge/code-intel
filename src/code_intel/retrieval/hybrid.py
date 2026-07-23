"""Hybrid retrieval engine.

Runs symbol search, keyword search, graph traversal, and (optional) vector
search, attributes each signal to a symbol, then combines them into a single
ranked, deduplicated result set. Scoring blends: semantic similarity, exact/
prefix match quality, keyword presence, graph proximity, cross-source consensus,
and recency. The vector source is skipped cleanly when no embeddings exist, so
retrieval degrades to deterministic-only rather than failing.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from code_intel.embeddings.provider import EmbeddingProvider
from code_intel.embeddings.sink import VectorHit
from code_intel.graph.builder import GraphBuilder
from code_intel.keyword_search.searcher import KeywordSearcher
from code_intel.models import Symbol
from code_intel.storage.repositories import FileStore, SymbolStore
from code_intel.symbols.index import SymbolIndex

# Source weights. Semantic and exact-symbol matches dominate; keyword and graph
# proximity refine; consensus and recency are light tie-breakers.
_W_SYMBOL = 0.30
_W_VECTOR = 0.35
_W_KEYWORD = 0.20
_W_GRAPH = 0.15
_W_RECENCY = 0.05
_CONSENSUS_STEP = 0.08

_SYMBOL_LIMIT = 25
_VECTOR_LIMIT = 25
_KEYWORD_LIMIT = 50
_GRAPH_SEEDS = 5
_GRAPH_SCORE = 0.5
_KEYWORD_STEP = 0.34


class VectorSearcher(Protocol):
    """Read side of a vector store (Qdrant or in-memory)."""

    def search(
        self, vector: list[float], limit: int = 10, payload_filter: dict[str, object] | None = None
    ) -> list[VectorHit]: ...


@dataclass(frozen=True)
class RetrievalResult:
    """One ranked, deduplicated retrieval hit with source provenance."""

    symbol_id: str
    name: str
    type: str
    path: str
    start_line: int
    end_line: int
    signature: str
    score: float
    sources: list[str]


@dataclass
class _Acc:
    symbol: float = 0.0
    vector: float = 0.0
    keyword: float = 0.0
    graph: float = 0.0
    sources: set[str] = field(default_factory=set)


class HybridRetriever:
    """Combines all retrieval sources for a repository."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        repository_id: str,
        repo_path: Path,
        *,
        vector_store: VectorSearcher | None = None,
        embed_provider: EmbeddingProvider | None = None,
    ) -> None:
        self._repo_id = repository_id
        self._symbols: dict[str, Symbol] = {
            s.id: s for s in SymbolStore(conn).list_for_repository(repository_id)
        }
        self._by_path: dict[str, list[Symbol]] = defaultdict(list)
        for symbol in self._symbols.values():
            self._by_path[symbol.path].append(symbol)
        self._index = SymbolIndex(conn)
        self._keyword = KeywordSearcher(repo_path, FileStore(conn).list_records(repository_id))
        self._graph = GraphBuilder(conn).build(repository_id)
        self._vector_store = vector_store
        self._embed_provider = embed_provider

    def retrieve(
        self,
        query: str,
        *,
        limit: int = 10,
        languages: list[str] | None = None,
        types: list[str] | None = None,
    ) -> list[RetrievalResult]:
        if not query.strip():
            return []
        acc: dict[str, _Acc] = defaultdict(_Acc)
        self._add_symbol_source(acc, query, languages, types)
        self._add_vector_source(acc, query)
        self._add_keyword_source(acc, query, languages)
        self._add_graph_source(acc)
        return self._rank(acc, limit, languages, types)

    # --- sources ---------------------------------------------------------

    def _add_symbol_source(
        self, acc: dict[str, _Acc], query: str, languages: list[str] | None, types: list[str] | None
    ) -> None:
        for hit in self._index.search(
            self._repo_id, query, languages=languages, types=types, limit=_SYMBOL_LIMIT
        ):
            acc[hit.id].symbol = max(acc[hit.id].symbol, hit.score)
            acc[hit.id].sources.add("symbol")

    def _add_vector_source(self, acc: dict[str, _Acc], query: str) -> None:
        if self._vector_store is None or self._embed_provider is None:
            return
        vectors = self._embed_provider.embed([query])
        if not vectors:
            return
        for hit in self._vector_store.search(vectors[0], limit=_VECTOR_LIMIT):
            if hit.symbol_id in self._symbols:
                acc[hit.symbol_id].vector = max(acc[hit.symbol_id].vector, hit.score)
                acc[hit.symbol_id].sources.add("vector")

    def _add_keyword_source(
        self, acc: dict[str, _Acc], query: str, languages: list[str] | None
    ) -> None:
        for match in self._keyword.search(query, languages=languages, limit=_KEYWORD_LIMIT):
            symbol = self._enclosing(match.path, match.line_number)
            if symbol is None:
                continue
            acc[symbol.id].keyword = min(1.0, acc[symbol.id].keyword + _KEYWORD_STEP)
            acc[symbol.id].sources.add("keyword")

    def _add_graph_source(self, acc: dict[str, _Acc]) -> None:
        seeds = sorted(acc.items(), key=lambda kv: -(kv[1].symbol + kv[1].vector))[:_GRAPH_SEEDS]
        for seed_id, _ in seeds:
            for node in self._graph.neighborhood(seed_id, depth=1).nodes:
                if node.id in self._symbols and node.id != seed_id:
                    acc[node.id].graph = max(acc[node.id].graph, _GRAPH_SCORE)
                    acc[node.id].sources.add("graph")

    # --- ranking ---------------------------------------------------------

    def _rank(
        self,
        acc: dict[str, _Acc],
        limit: int,
        languages: list[str] | None,
        types: list[str] | None,
    ) -> list[RetrievalResult]:
        candidates = {
            sid: data
            for sid, data in acc.items()
            if sid in self._symbols and self._passes(self._symbols[sid], languages, types)
        }
        recency = self._recency_scores(candidates)
        results = [
            self._build_result(sid, data, recency[sid]) for sid, data in candidates.items()
        ]
        results.sort(key=lambda r: (-r.score, r.path, r.start_line))
        return results[:limit]

    def _build_result(self, symbol_id: str, data: _Acc, recency: float) -> RetrievalResult:
        base = (
            _W_SYMBOL * data.symbol
            + _W_VECTOR * data.vector
            + _W_KEYWORD * data.keyword
            + _W_GRAPH * data.graph
            + _W_RECENCY * recency
        )
        consensus = 1.0 + _CONSENSUS_STEP * (len(data.sources) - 1)
        symbol = self._symbols[symbol_id]
        return RetrievalResult(
            symbol_id=symbol_id,
            name=symbol.name,
            type=symbol.type,
            path=symbol.path,
            start_line=symbol.start_line,
            end_line=symbol.end_line,
            signature=symbol.signature,
            score=round(base * consensus, 4),
            sources=sorted(data.sources),
        )

    def _recency_scores(self, candidates: dict[str, _Acc]) -> dict[str, float]:
        if not candidates:
            return {}
        ordered = sorted(candidates, key=lambda sid: self._symbols[sid].updated_at)
        n = len(ordered)
        if n == 1:
            return {ordered[0]: 1.0}
        return {sid: rank / (n - 1) for rank, sid in enumerate(ordered)}

    def _enclosing(self, path: str, line: int) -> Symbol | None:
        best: Symbol | None = None
        for symbol in self._by_path.get(path, ()):
            if symbol.start_line <= line <= symbol.end_line and (
                best is None
                or (symbol.end_line - symbol.start_line) < (best.end_line - best.start_line)
            ):
                best = symbol
        return best

    @staticmethod
    def _passes(symbol: Symbol, languages: list[str] | None, types: list[str] | None) -> bool:
        if languages and symbol.language not in languages:
            return False
        return not (types and symbol.type not in types)
