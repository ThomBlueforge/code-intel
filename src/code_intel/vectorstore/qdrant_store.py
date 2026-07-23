"""Qdrant-backed vector store (embedded/local mode).

Uses Qdrant's local persistence (``QdrantClient(path=...)``) so the platform
stays server-free and local-first. Supports incremental upsert, delete,
re-index, metadata-filtered search, and count. A symbol's UUID is used directly
as the point id, so upserting the same symbol overwrites its vector in place.
"""

from __future__ import annotations

from pathlib import Path
from types import TracebackType

from qdrant_client import QdrantClient, models

from code_intel.embeddings.sink import EmbeddedUnit, VectorHit

DEFAULT_COLLECTION = "symbols"


class QdrantVectorStore:
    """A local Qdrant collection implementing the ``VectorSink`` protocol."""

    def __init__(
        self,
        path: Path,
        dimension: int,
        collection: str = DEFAULT_COLLECTION,
        client: QdrantClient | None = None,
    ) -> None:
        self._collection = collection
        self._dimension = dimension
        self._owns_client = client is None
        path.mkdir(parents=True, exist_ok=True)
        self._client = client or QdrantClient(path=str(path))
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        if not self._client.collection_exists(self._collection):
            self._client.create_collection(
                self._collection,
                vectors_config=models.VectorParams(
                    size=self._dimension, distance=models.Distance.COSINE
                ),
            )

    def upsert(self, units: list[EmbeddedUnit]) -> None:
        if not units:
            return
        points = [
            models.PointStruct(
                id=unit.symbol_id,
                vector=unit.vector,
                payload={**unit.payload, "symbol_id": unit.symbol_id},
            )
            for unit in units
        ]
        self._client.upsert(self._collection, points=points)

    def delete(self, symbol_ids: list[str]) -> None:
        if not symbol_ids:
            return
        self._client.delete(
            self._collection,
            points_selector=models.PointIdsList(points=list(symbol_ids)),
        )

    def search(
        self,
        vector: list[float],
        limit: int = 10,
        payload_filter: dict[str, object] | None = None,
    ) -> list[VectorHit]:
        result = self._client.query_points(
            self._collection,
            query=vector,
            limit=limit,
            query_filter=_build_filter(payload_filter),
            with_payload=True,
        )
        return [
            VectorHit(
                symbol_id=str(point.id),
                score=float(point.score),
                payload=dict(point.payload or {}),
            )
            for point in result.points
        ]

    def count(self) -> int:
        return int(self._client.count(self._collection).count)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> QdrantVectorStore:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


def _build_filter(payload_filter: dict[str, object] | None) -> models.Filter | None:
    if not payload_filter:
        return None
    conditions: list[models.Condition] = [
        models.FieldCondition(key=key, match=models.MatchValue(value=value))  # type: ignore[arg-type]
        for key, value in payload_filter.items()
    ]
    return models.Filter(must=conditions)
