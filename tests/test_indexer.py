"""Tests for incremental indexing end-to-end."""

from __future__ import annotations

from pathlib import Path

from code_intel.config import Settings
from code_intel.ingestion.indexer import Indexer
from code_intel.storage.database import Database
from code_intel.storage.repositories import FileStore, RepositoryStore


def _settings(repo: Path, tmp_path: Path) -> Settings:
    return Settings.for_repository(repo, db_path=tmp_path / "index.db")


def test_first_index_adds_all_known_files(sample_repo: Path, tmp_path: Path) -> None:
    report = Indexer(_settings(sample_repo, tmp_path)).index(sample_repo)
    assert report.added == 4  # main.py, app.ts, README.md, query.sql
    assert report.changed == 0
    assert report.removed == 0
    assert report.total_indexed == 4


def test_reindex_no_changes_touches_nothing(sample_repo: Path, tmp_path: Path) -> None:
    settings = _settings(sample_repo, tmp_path)
    Indexer(settings).index(sample_repo)
    report = Indexer(settings).index(sample_repo)
    assert report.added == 0
    assert report.changed == 0
    assert report.removed == 0
    assert report.unchanged == 4
    assert report.touched == 0


def test_reindex_detects_changed_file(sample_repo: Path, tmp_path: Path) -> None:
    settings = _settings(sample_repo, tmp_path)
    Indexer(settings).index(sample_repo)
    (sample_repo / "src" / "main.py").write_text("def main():\n    return 2\n", encoding="utf-8")
    report = Indexer(settings).index(sample_repo)
    assert report.changed == 1
    assert report.added == 0
    assert report.unchanged == 3


def test_reindex_detects_added_and_removed(sample_repo: Path, tmp_path: Path) -> None:
    settings = _settings(sample_repo, tmp_path)
    Indexer(settings).index(sample_repo)
    (sample_repo / "src" / "extra.go").write_text("package main\n", encoding="utf-8")
    (sample_repo / "query.sql").unlink()
    report = Indexer(settings).index(sample_repo)
    assert report.added == 1
    assert report.removed == 1


def test_manifest_persisted_and_queryable_by_path(sample_repo: Path, tmp_path: Path) -> None:
    settings = _settings(sample_repo, tmp_path)
    result = Indexer(settings).index(sample_repo)
    with Database(settings.db_path) as db:
        repo = RepositoryStore(db.connection).get_by_path(str(sample_repo.resolve()))
        assert repo is not None
        manifest = FileStore(db.connection).manifest(repo.id)
    assert set(manifest) == {"src/main.py", "src/app.ts", "README.md", "query.sql"}
    assert result.repository_id == repo.id


def test_removed_file_hash_row_deleted(sample_repo: Path, tmp_path: Path) -> None:
    settings = _settings(sample_repo, tmp_path)
    Indexer(settings).index(sample_repo)
    (sample_repo / "query.sql").unlink()
    Indexer(settings).index(sample_repo)
    with Database(settings.db_path) as db:
        repo = RepositoryStore(db.connection).get_by_path(str(sample_repo.resolve()))
        assert repo is not None
        manifest = FileStore(db.connection).manifest(repo.id)
    assert "query.sql" not in manifest
