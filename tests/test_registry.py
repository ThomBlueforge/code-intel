"""Tests for the user-level repository registry (U1)."""

from __future__ import annotations

from pathlib import Path

from code_intel.registry import RepositoryRegistry


def test_record_list_remove(tmp_path: Path) -> None:
    registry = RepositoryRegistry(tmp_path / "registry.json")
    repo = tmp_path / "r"
    repo.mkdir()
    db = repo / ".code-intel" / "index.db"

    entry = registry.record(repo_path=repo, name="r", db_path=db)
    assert entry.path == str(repo.resolve())
    assert entry.db_path == str(db.resolve())

    listed = registry.list()
    assert len(listed) == 1
    assert listed[0].name == "r"

    assert registry.remove(repo) is True
    assert registry.list() == []
    assert registry.remove(repo) is False  # already gone


def test_record_is_idempotent_by_path(tmp_path: Path) -> None:
    registry = RepositoryRegistry(tmp_path / "registry.json")
    repo = tmp_path / "r"
    repo.mkdir()
    db = repo / ".code-intel" / "index.db"

    registry.record(repo_path=repo, name="r", db_path=db)
    registry.record(repo_path=repo, name="r-renamed", db_path=db)

    listed = registry.list()
    assert len(listed) == 1
    assert listed[0].name == "r-renamed"


def test_corrupt_registry_is_ignored(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    path.write_text("this is not json", encoding="utf-8")
    registry = RepositoryRegistry(path)
    assert registry.list() == []


def test_missing_registry_reads_empty(tmp_path: Path) -> None:
    registry = RepositoryRegistry(tmp_path / "does-not-exist.json")
    assert registry.list() == []
