"""Tests for symbol persistence through the incremental indexer."""

from __future__ import annotations

from pathlib import Path

from code_intel.config import Settings
from code_intel.ingestion.indexer import Indexer
from code_intel.storage.database import Database
from code_intel.storage.repositories import RepositoryStore, SymbolStore


def _settings(repo: Path, tmp_path: Path) -> Settings:
    return Settings.for_repository(repo, db_path=tmp_path / "index.db")


def _symbols_for(settings: Settings, repo: Path, rel_path: str) -> list:
    with Database(settings.db_path) as db:
        repo_row = RepositoryStore(db.connection).get_by_path(str(repo.resolve()))
        assert repo_row is not None
        return SymbolStore(db.connection).list_for_path(repo_row.id, rel_path)


def test_index_populates_symbols_queryable_by_path(sample_repo: Path, tmp_path: Path) -> None:
    settings = _settings(sample_repo, tmp_path)
    report = Indexer(settings).index(sample_repo)
    assert report.symbols_total > 0
    symbols = _symbols_for(settings, sample_repo, "src/main.py")
    names = {s.name for s in symbols}
    assert "main" in names


def test_reindex_unchanged_does_not_reparse(sample_repo: Path, tmp_path: Path) -> None:
    settings = _settings(sample_repo, tmp_path)
    Indexer(settings).index(sample_repo)
    report = Indexer(settings).index(sample_repo)
    assert report.symbols_parsed == 0  # nothing changed -> nothing parsed
    assert report.symbols_total > 0  # but symbols persist


def test_changed_file_symbols_are_replaced(sample_repo: Path, tmp_path: Path) -> None:
    settings = _settings(sample_repo, tmp_path)
    Indexer(settings).index(sample_repo)
    (sample_repo / "src" / "main.py").write_text(
        "def main():\n    return 1\n\ndef helper():\n    return 2\n", encoding="utf-8"
    )
    Indexer(settings).index(sample_repo)
    names = {s.name for s in _symbols_for(settings, sample_repo, "src/main.py")}
    assert names == {"main", "helper"}


def test_removed_file_symbols_cascade_deleted(sample_repo: Path, tmp_path: Path) -> None:
    settings = _settings(sample_repo, tmp_path)
    # Add a Go file with symbols, then remove it and confirm its symbols vanish.
    (sample_repo / "svc.go").write_text("package m\nfunc Handle() {}\n", encoding="utf-8")
    Indexer(settings).index(sample_repo)
    assert _symbols_for(settings, sample_repo, "svc.go")
    (sample_repo / "svc.go").unlink()
    Indexer(settings).index(sample_repo)
    assert _symbols_for(settings, sample_repo, "svc.go") == []


def test_parent_links_resolve_within_file(sample_repo: Path, tmp_path: Path) -> None:
    settings = _settings(sample_repo, tmp_path)
    (sample_repo / "mod.py").write_text(
        "class Service:\n    def run(self):\n        return 1\n", encoding="utf-8"
    )
    Indexer(settings).index(sample_repo)
    symbols = {s.name: s for s in _symbols_for(settings, sample_repo, "mod.py")}
    assert symbols["run"].type == "method"
    assert symbols["run"].parent_id == symbols["Service"].id
