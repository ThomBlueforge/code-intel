"""Tests for ranked symbol search."""

from __future__ import annotations

import time
from pathlib import Path

from code_intel.config import Settings
from code_intel.ingestion.indexer import Indexer
from code_intel.storage.database import Database
from code_intel.storage.repositories import RepositoryStore
from code_intel.symbols.index import SymbolIndex


def _indexed(tmp_path: Path) -> tuple[Settings, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "auth.py").write_text(
        "def authenticate(user):\n    return True\n\n"
        "def authorize(user):\n    return True\n\n"
        "class AuthService:\n    def login(self):\n        return 1\n",
        encoding="utf-8",
    )
    (repo / "handler.go").write_text(
        "package m\nfunc Authenticate() {}\n", encoding="utf-8"
    )
    settings = Settings.for_repository(repo, db_path=tmp_path / "index.db")
    Indexer(settings).index(repo)
    with Database(settings.db_path) as db:
        row = RepositoryStore(db.connection).get_by_path(str(repo.resolve()))
        assert row is not None
        return settings, row.id


def _search(settings: Settings, repo_id: str, query: str, **kwargs: object) -> list:
    with Database(settings.db_path) as db:
        return SymbolIndex(db.connection).search(repo_id, query, **kwargs)  # type: ignore[arg-type]


def test_exact_match_ranks_first(tmp_path: Path) -> None:
    settings, repo_id = _indexed(tmp_path)
    hits = _search(settings, repo_id, "login")
    assert hits[0].name == "login"
    assert hits[0].match_type == "exact"
    assert hits[0].score == 1.0


def test_prefix_match(tmp_path: Path) -> None:
    settings, repo_id = _indexed(tmp_path)
    names = {h.name for h in _search(settings, repo_id, "auth")}
    assert {"authenticate", "authorize", "AuthService"}.issubset(names)


def test_fuzzy_match_tolerates_typo(tmp_path: Path) -> None:
    settings, repo_id = _indexed(tmp_path)
    hits = _search(settings, repo_id, "authenticat")  # missing trailing e
    assert any(h.name == "authenticate" for h in hits)


def test_filter_by_language(tmp_path: Path) -> None:
    settings, repo_id = _indexed(tmp_path)
    hits = _search(settings, repo_id, "authenticate", languages=["Go"])
    assert all(h.language == "Go" for h in hits)
    assert any(h.name == "Authenticate" for h in hits)


def test_filter_by_type(tmp_path: Path) -> None:
    settings, repo_id = _indexed(tmp_path)
    hits = _search(settings, repo_id, "auth", types=["class"])
    assert all(h.type == "class" for h in hits)
    assert any(h.name == "AuthService" for h in hits)


def test_empty_query_returns_nothing(tmp_path: Path) -> None:
    settings, repo_id = _indexed(tmp_path)
    assert _search(settings, repo_id, "   ") == []


def test_search_is_fast(tmp_path: Path) -> None:
    settings, repo_id = _indexed(tmp_path)
    with Database(settings.db_path) as db:
        index = SymbolIndex(db.connection)
        start = time.perf_counter()
        index.search(repo_id, "auth")
        elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms < 200
