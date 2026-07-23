"""Tests for hierarchical summaries / explain (Phase 11)."""

from __future__ import annotations

from pathlib import Path

from code_intel.config import Settings
from code_intel.ingestion.indexer import Indexer
from code_intel.storage.database import Database
from code_intel.storage.repositories import RepositoryStore, SummaryStore
from code_intel.understanding.summaries import SummaryBuilder


def _indexed(tmp_path: Path) -> tuple[Settings, str]:
    repo = tmp_path / "repo"
    (repo / "pkg").mkdir(parents=True)
    (repo / "pkg" / "svc.py").write_text(
        "class Service:\n    def run(self):\n        return 1\n\ndef helper():\n    return 2\n",
        encoding="utf-8",
    )
    settings = Settings.for_repository(repo, db_path=tmp_path / "index.db")
    Indexer(settings).index(repo)
    with Database(settings.db_path) as db:
        row = RepositoryStore(db.connection).get_by_path(str(repo.resolve()))
        assert row is not None
        return settings, row.id


def test_build_repository_persists_all_levels(tmp_path: Path) -> None:
    settings, repo_id = _indexed(tmp_path)
    with Database(settings.db_path) as db:
        written = SummaryBuilder(db.connection).build_repository(repo_id)
        stored = SummaryStore(db.connection).count()
    assert written > 0
    assert stored == written
    # Levels present: symbol scopes + module + package + repository.
    with Database(settings.db_path) as db:
        repo_summary = SummaryStore(db.connection).get("repository", repo_id)
    assert repo_summary is not None
    assert "Repository" in repo_summary.summary


def test_explain_module_and_symbol(tmp_path: Path) -> None:
    settings, repo_id = _indexed(tmp_path)
    with Database(settings.db_path) as db:
        builder = SummaryBuilder(db.connection)
        module = builder.explain(repo_id, "pkg/svc.py")
        symbol = builder.explain(repo_id, "helper")
        repo = builder.explain(repo_id, ".")
    assert module is not None and module.scope == "module"
    assert "svc.py" in module.summary
    assert symbol is not None and symbol.scope == "function"
    assert repo is not None and repo.scope == "repository"


def test_explain_unknown_returns_none(tmp_path: Path) -> None:
    settings, repo_id = _indexed(tmp_path)
    with Database(settings.db_path) as db:
        assert SummaryBuilder(db.connection).explain(repo_id, "nope/missing.py") is None
