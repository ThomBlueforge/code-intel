"""Tests for AI enrichment using a fake chat client (no network)."""

from __future__ import annotations

import json
from pathlib import Path

from code_intel.config import Settings
from code_intel.enrichment.enricher import Enricher
from code_intel.ingestion.indexer import Indexer
from code_intel.llm.client import ChatMessage
from code_intel.storage.database import Database
from code_intel.storage.repositories import EnrichedSymbolStore, RepositoryStore, SymbolStore


class FakeChatClient:
    """Returns a canned response; records the last messages it received."""

    def __init__(self, response: str) -> None:
        self._response = response
        self.calls = 0

    def complete(self, messages: list[ChatMessage]) -> str:
        self.calls += 1
        return self._response


_GOOD_RESPONSE = json.dumps(
    {
        "summary": "Authenticates a user.",
        "business_domain": ["Authentication", "NotARealDomain"],
        "architecture_layer": "Security",
        "responsibilities": ["Authentication", "Validation", "Nonsense"],
        "quality_metrics": {
            "complexity": 0.3, "maintainability": 0.8, "readability": 0.9,
            "coupling": 0.2, "cohesion": 0.7, "testability": 0.6, "risk": 0.1,
            "stability": 0.9, "reusability": 0.5, "technical_debt": 0.1,
        },
        "risks": ["No rate limiting"],
        "technical_debt": [],
        "confidence": 0.82,
    }
)


def _indexed(tmp_path: Path) -> tuple[Settings, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "auth.py").write_text(
        "def authenticate(user):\n    return check(user)\n", encoding="utf-8"
    )
    settings = Settings.for_repository(repo, db_path=tmp_path / "index.db")
    Indexer(settings).index(repo)
    with Database(settings.db_path) as db:
        row = RepositoryStore(db.connection).get_by_path(str(repo.resolve()))
        assert row is not None
        return settings, row.id


def test_enrich_symbol_parses_and_coerces_ontology(tmp_path: Path) -> None:
    settings, repo_id = _indexed(tmp_path)
    client = FakeChatClient(_GOOD_RESPONSE)
    with Database(settings.db_path) as db:
        symbol = SymbolStore(db.connection).find_by_name(repo_id, "authenticate")[0]
        enriched = Enricher(db.connection, client, "test-model").enrich_symbol(symbol)
    assert enriched.summary == "Authenticates a user."
    # Out-of-vocabulary labels are dropped; valid ones kept.
    assert enriched.business_domain == ["Authentication"]
    assert enriched.architecture_layer == "Security"
    assert set(enriched.responsibilities) == {"Authentication", "Validation"}
    assert enriched.confidence == 0.82
    assert enriched.quality_metrics.maintainability == 0.8


def test_enrich_repository_persists_separately_joinable_by_symbol_id(tmp_path: Path) -> None:
    settings, repo_id = _indexed(tmp_path)
    client = FakeChatClient(_GOOD_RESPONSE)
    with Database(settings.db_path) as db:
        conn = db.connection
        report = Enricher(conn, client, "test-model").enrich_repository(repo_id)
        assert report.enriched >= 1
        assert report.total_enriched_in_repo >= 1
        # Enrichment is joinable to the deterministic symbol by id.
        symbol = SymbolStore(conn).find_by_name(repo_id, "authenticate")[0]
        stored = EnrichedSymbolStore(conn).get(symbol.id)
    assert stored is not None
    assert stored.symbol_id == symbol.id
    assert stored.summary == "Authenticates a user."


def test_malformed_response_degrades_to_unknown(tmp_path: Path) -> None:
    settings, repo_id = _indexed(tmp_path)
    client = FakeChatClient("the model rambled without any JSON")
    with Database(settings.db_path) as db:
        symbol = SymbolStore(db.connection).find_by_name(repo_id, "authenticate")[0]
        enriched = Enricher(db.connection, client, "test-model").enrich_symbol(symbol)
    assert enriched.summary == "Unknown"
    assert enriched.confidence == 0.0
    assert enriched.business_domain == ["Unknown"]


def test_reenrich_skips_already_enriched_unless_forced(tmp_path: Path) -> None:
    settings, repo_id = _indexed(tmp_path)
    client = FakeChatClient(_GOOD_RESPONSE)
    with Database(settings.db_path) as db:
        conn = db.connection
        enricher = Enricher(conn, client, "test-model")
        enricher.enrich_repository(repo_id)
        calls_after_first = client.calls
        second = enricher.enrich_repository(repo_id)
        assert second.enriched == 0  # all already enriched
        assert client.calls == calls_after_first  # no new LLM calls
        third = enricher.enrich_repository(repo_id, force=True)
        assert third.enriched >= 1
        assert client.calls > calls_after_first


def test_deterministic_layer_untouched_by_enrichment(tmp_path: Path) -> None:
    """Symbols remain intact and independent of enrichment."""
    settings, repo_id = _indexed(tmp_path)
    with Database(settings.db_path) as db:
        before = len(SymbolStore(db.connection).list_for_repository(repo_id))
        Enricher(db.connection, FakeChatClient(_GOOD_RESPONSE), "m").enrich_repository(repo_id)
        after = len(SymbolStore(db.connection).list_for_repository(repo_id))
    assert before == after
