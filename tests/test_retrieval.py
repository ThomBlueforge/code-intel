"""Tests for hybrid retrieval."""

from __future__ import annotations

import json
from pathlib import Path

from code_intel.config import Settings
from code_intel.embeddings.pipeline import EmbeddingPipeline
from code_intel.embeddings.provider import HashingEmbeddingProvider
from code_intel.embeddings.sink import InMemoryVectorSink
from code_intel.enrichment.enricher import Enricher
from code_intel.ingestion.indexer import Indexer
from code_intel.llm.client import ChatMessage
from code_intel.retrieval.hybrid import HybridRetriever
from code_intel.storage.database import Database
from code_intel.storage.repositories import RepositoryStore


class FakeChatClient:
    def complete(self, messages: list[ChatMessage]) -> str:
        return json.dumps(
            {
                "summary": "Handles authentication.",
                "business_domain": ["Authentication"],
                "architecture_layer": "Security",
                "responsibilities": ["Authentication"],
                "quality_metrics": {"complexity": 0.2},
                "risks": [],
                "technical_debt": [],
                "confidence": 0.8,
            }
        )


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "auth.py").write_text(
        "def authenticate(user):\n    return validate(user)\n\n"
        "def validate(user):\n    return True\n\n"
        "class AuthService:\n    def login(self):\n        return authenticate(self)\n",
        encoding="utf-8",
    )
    (repo / "billing.py").write_text(
        "def charge_card(amount):\n    return amount\n", encoding="utf-8"
    )
    return repo


def _indexed(tmp_path: Path) -> tuple[Settings, str]:
    repo = _repo(tmp_path)
    settings = Settings.for_repository(repo, db_path=tmp_path / "index.db")
    Indexer(settings).index(repo)
    with Database(settings.db_path) as db:
        row = RepositoryStore(db.connection).get_by_path(str(repo.resolve()))
        assert row is not None
        return settings, row.id


def test_retrieve_deterministic_only(tmp_path: Path) -> None:
    """Without embeddings, retrieval still works from symbol/keyword/graph."""
    settings, repo_id = _indexed(tmp_path)
    repo = settings.db_path.parent / "repo"
    with Database(settings.db_path) as db:
        retriever = HybridRetriever(db.connection, repo_id, repo)
        results = retriever.retrieve("authenticate", limit=5)
    assert results
    top = results[0]
    assert top.name == "authenticate"
    assert "symbol" in top.sources


def test_retrieve_merges_and_dedupes_sources(tmp_path: Path) -> None:
    settings, repo_id = _indexed(tmp_path)
    repo = settings.db_path.parent / "repo"
    with Database(settings.db_path) as db:
        retriever = HybridRetriever(db.connection, repo_id, repo)
        results = retriever.retrieve("authenticate", limit=10)
    ids = [r.symbol_id for r in results]
    assert len(ids) == len(set(ids))  # deduplicated
    # authenticate is found by symbol name AND keyword AND graph (called by login).
    top = next(r for r in results if r.name == "authenticate")
    assert {"symbol", "keyword"}.issubset(set(top.sources))


def test_graph_pulls_in_related_symbols(tmp_path: Path) -> None:
    settings, repo_id = _indexed(tmp_path)
    repo = settings.db_path.parent / "repo"
    with Database(settings.db_path) as db:
        retriever = HybridRetriever(db.connection, repo_id, repo)
        results = retriever.retrieve("AuthService", limit=10)
    names = {r.name for r in results}
    # The class's methods are reachable via graph proximity.
    assert "login" in names


def test_type_and_language_filters(tmp_path: Path) -> None:
    settings, repo_id = _indexed(tmp_path)
    repo = settings.db_path.parent / "repo"
    with Database(settings.db_path) as db:
        retriever = HybridRetriever(db.connection, repo_id, repo)
        only_classes = retriever.retrieve("auth", limit=10, types=["class"])
    assert only_classes
    assert all(r.type == "class" for r in only_classes)


def test_retrieve_with_vector_source(tmp_path: Path) -> None:
    settings, repo_id = _indexed(tmp_path)
    repo = settings.db_path.parent / "repo"
    provider = HashingEmbeddingProvider()
    sink = InMemoryVectorSink()
    with Database(settings.db_path) as db:
        conn = db.connection
        Enricher(conn, FakeChatClient(), "m").enrich_repository(repo_id)
        EmbeddingPipeline(conn, provider, "hashing").run(repo_id, sink)
        retriever = HybridRetriever(
            conn, repo_id, repo, vector_store=sink, embed_provider=provider
        )
        results = retriever.retrieve("authenticate", limit=5)
    assert results
    assert any("vector" in r.sources for r in results)


def test_empty_query_returns_nothing(tmp_path: Path) -> None:
    settings, repo_id = _indexed(tmp_path)
    repo = settings.db_path.parent / "repo"
    with Database(settings.db_path) as db:
        retriever = HybridRetriever(db.connection, repo_id, repo)
        assert retriever.retrieve("   ") == []
