"""Embedded units and the vector sink interface.

``EmbeddedUnit`` is the payload handed from the embedding pipeline to a vector
store. ``VectorSink`` is the narrow write interface a store must implement so the
pipeline never depends on Qdrant directly. ``InMemoryVectorSink`` is a reference
implementation used for tests and offline runs; it also supports a naive cosine
search so retrieval can be exercised without a real vector database.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class EmbeddedUnit:
    """A fully-embedded logical unit ready for the vector store."""

    symbol_id: str
    vector: list[float]
    content_hash: str
    model: str
    dimension: int
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class VectorHit:
    """A vector-search result."""

    symbol_id: str
    score: float
    payload: dict[str, object]


class VectorSink(Protocol):
    """Write side of a vector store."""

    def upsert(self, units: list[EmbeddedUnit]) -> None: ...

    def delete(self, symbol_ids: list[str]) -> None: ...


class InMemoryVectorSink:
    """Dictionary-backed sink with naive cosine search (tests / offline)."""

    def __init__(self) -> None:
        self._units: dict[str, EmbeddedUnit] = {}

    def upsert(self, units: list[EmbeddedUnit]) -> None:
        for unit in units:
            self._units[unit.symbol_id] = unit

    def delete(self, symbol_ids: list[str]) -> None:
        for symbol_id in symbol_ids:
            self._units.pop(symbol_id, None)

    def __len__(self) -> int:
        return len(self._units)

    def search(
        self, vector: list[float], limit: int = 10, payload_filter: dict[str, object] | None = None
    ) -> list[VectorHit]:
        hits: list[VectorHit] = []
        for unit in self._units.values():
            if payload_filter and not _matches(unit.payload, payload_filter):
                continue
            hits.append(
                VectorHit(unit.symbol_id, _cosine(vector, unit.vector), dict(unit.payload))
            )
        hits.sort(key=lambda h: -h.score)
        return hits[:limit]


def _matches(payload: dict[str, object], payload_filter: dict[str, object]) -> bool:
    return all(payload.get(key) == value for key, value in payload_filter.items())


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)
