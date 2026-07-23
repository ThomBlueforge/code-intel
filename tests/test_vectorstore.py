"""Tests for the Qdrant vector store (embedded/local mode)."""

from __future__ import annotations

from pathlib import Path

from code_intel.embeddings.sink import EmbeddedUnit
from code_intel.vectorstore.qdrant_store import QdrantVectorStore


def _unit(symbol_id: str, vector: list[float], **payload: object) -> EmbeddedUnit:
    return EmbeddedUnit(
        symbol_id=symbol_id,
        vector=vector,
        content_hash="h",
        model="test",
        dimension=len(vector),
        payload=payload,
    )


def test_upsert_and_search(tmp_path: Path) -> None:
    with QdrantVectorStore(tmp_path / "q", dimension=3) as store:
        store.upsert(
            [
                _unit("11111111-1111-1111-1111-111111111111", [1.0, 0.0, 0.0], language="Python"),
                _unit("22222222-2222-2222-2222-222222222222", [0.0, 1.0, 0.0], language="Go"),
            ]
        )
        assert store.count() == 2
        hits = store.search([1.0, 0.0, 0.0], limit=1)
        assert hits[0].symbol_id == "11111111-1111-1111-1111-111111111111"
        assert hits[0].payload["language"] == "Python"


def test_metadata_filtered_search(tmp_path: Path) -> None:
    with QdrantVectorStore(tmp_path / "q", dimension=3) as store:
        store.upsert(
            [
                _unit("11111111-1111-1111-1111-111111111111", [1.0, 0.1, 0.0], language="Python"),
                _unit("22222222-2222-2222-2222-222222222222", [1.0, 0.0, 0.1], language="Go"),
            ]
        )
        # The nearest vector is the Python one, but we filter to Go only.
        hits = store.search([1.0, 0.1, 0.0], limit=5, payload_filter={"language": "Go"})
        assert len(hits) == 1
        assert hits[0].payload["language"] == "Go"


def test_incremental_update_reflects_current_state(tmp_path: Path) -> None:
    qpath = tmp_path / "q"
    with QdrantVectorStore(qpath, dimension=3) as store:
        store.upsert([_unit("11111111-1111-1111-1111-111111111111", [1.0, 0.0, 0.0], v="old")])
        # Overwrite the same symbol id with a new vector + payload (incremental).
        store.upsert([_unit("11111111-1111-1111-1111-111111111111", [0.0, 1.0, 0.0], v="new")])
        assert store.count() == 1  # not duplicated
        hits = store.search([0.0, 1.0, 0.0], limit=1)
        assert hits[0].payload["v"] == "new"  # current, not stale


def test_delete_removes_points(tmp_path: Path) -> None:
    with QdrantVectorStore(tmp_path / "q", dimension=3) as store:
        store.upsert(
            [
                _unit("11111111-1111-1111-1111-111111111111", [1.0, 0.0, 0.0]),
                _unit("22222222-2222-2222-2222-222222222222", [0.0, 1.0, 0.0]),
            ]
        )
        store.delete(["11111111-1111-1111-1111-111111111111"])
        assert store.count() == 1
        remaining = store.search([0.0, 1.0, 0.0], limit=5)
        assert {h.symbol_id for h in remaining} == {"22222222-2222-2222-2222-222222222222"}


def test_reopening_persists_data(tmp_path: Path) -> None:
    qpath = tmp_path / "q"
    with QdrantVectorStore(qpath, dimension=3) as store:
        store.upsert([_unit("11111111-1111-1111-1111-111111111111", [1.0, 0.0, 0.0])])
    # Reopen a fresh client on the same path — data survives.
    with QdrantVectorStore(qpath, dimension=3) as reopened:
        assert reopened.count() == 1
