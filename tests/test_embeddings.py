"""Tests for the embedding pipeline (offline hashing provider)."""

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
from code_intel.storage.database import Database
from code_intel.storage.repositories import EmbeddingStore, RepositoryStore, SymbolStore


class FakeChatClient:
    def __init__(self, response: str) -> None:
        self._response = response

    def complete(self, messages: list[ChatMessage]) -> str:
        return self._response


_ENRICH = json.dumps(
    {
        "summary": "Does a thing.",
        "business_domain": ["Users"],
        "architecture_layer": "Service",
        "responsibilities": ["Business Logic"],
        "quality_metrics": {"complexity": 0.4},
        "risks": [],
        "technical_debt": [],
        "confidence": 0.7,
    }
)


def _prepared(tmp_path: Path) -> tuple[Settings, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "svc.py").write_text(
        "def create_user(name):\n    return name\n\n"
        "def delete_user(name):\n    return name\n",
        encoding="utf-8",
    )
    settings = Settings.for_repository(repo, db_path=tmp_path / "index.db")
    Indexer(settings).index(repo)
    with Database(settings.db_path) as db:
        conn = db.connection
        repo_row = RepositoryStore(conn).get_by_path(str(repo.resolve()))
        assert repo_row is not None
        Enricher(conn, FakeChatClient(_ENRICH), "m").enrich_repository(repo_row.id)
        return settings, repo_row.id


def test_hashing_provider_is_deterministic_and_normalized() -> None:
    provider = HashingEmbeddingProvider(dimension=64)
    a = provider.embed(["create user account"])[0]
    b = provider.embed(["create user account"])[0]
    assert a == b
    assert len(a) == 64
    assert abs(sum(x * x for x in a) - 1.0) < 1e-6


def test_every_enriched_symbol_gets_embedding_record(tmp_path: Path) -> None:
    settings, repo_id = _prepared(tmp_path)
    sink = InMemoryVectorSink()
    with Database(settings.db_path) as db:
        conn = db.connection
        report = EmbeddingPipeline(conn, HashingEmbeddingProvider(), "hashing").run(repo_id, sink)
        enriched_count = len(
            [s for s in SymbolStore(conn).list_for_repository(repo_id) if s.type in {"function"}]
        )
        records = EmbeddingStore(conn).count()
    assert report.embedded == enriched_count
    assert records == enriched_count
    assert len(sink) == enriched_count


def test_embedding_record_is_traceable_by_symbol_id(tmp_path: Path) -> None:
    settings, repo_id = _prepared(tmp_path)
    sink = InMemoryVectorSink()
    with Database(settings.db_path) as db:
        conn = db.connection
        EmbeddingPipeline(conn, HashingEmbeddingProvider(), "hashing").run(repo_id, sink)
        symbol = SymbolStore(conn).find_by_name(repo_id, "create_user")[0]
        record = EmbeddingStore(conn).get(symbol.id)
    assert record is not None
    assert record.symbol_id == symbol.id
    assert record.dimension == 256


def test_unit_payload_carries_metadata(tmp_path: Path) -> None:
    settings, repo_id = _prepared(tmp_path)
    sink = InMemoryVectorSink()
    with Database(settings.db_path) as db:
        conn = db.connection
        EmbeddingPipeline(conn, HashingEmbeddingProvider(), "hashing").run(repo_id, sink)
        symbol = SymbolStore(conn).find_by_name(repo_id, "create_user")[0]
    hits = sink.search(HashingEmbeddingProvider().embed(["create user"])[0], limit=1)
    assert hits
    payload = sink._units[symbol.id].payload  # noqa: SLF001 - test introspection
    assert payload["name"] == "create_user"
    assert payload["business_domain"] == ["Users"]
    assert "create" in payload["keywords"]


def test_reembed_skips_unchanged_unless_forced(tmp_path: Path) -> None:
    settings, repo_id = _prepared(tmp_path)
    with Database(settings.db_path) as db:
        conn = db.connection
        pipe = EmbeddingPipeline(conn, HashingEmbeddingProvider(), "hashing")
        first = pipe.run(repo_id, InMemoryVectorSink())
        second = pipe.run(repo_id, InMemoryVectorSink())
        assert second.embedded == 0
        forced = pipe.run(repo_id, InMemoryVectorSink(), force=True)
        assert forced.embedded == first.embedded
