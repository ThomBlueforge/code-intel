"""Tests for bottom-up codebase comprehension (Phase 23)."""

from __future__ import annotations

import json
from pathlib import Path

from code_intel.config import Settings
from code_intel.ingestion.indexer import Indexer
from code_intel.llm.client import ChatMessage
from code_intel.storage.database import Database
from code_intel.storage.repositories import (
    FileUnderstandingStore,
    RepositoryStore,
    RepoUnderstandingStore,
)
from code_intel.understanding.comprehension import ComprehensionBuilder


class FakeChatClient:
    """Returns file/repo JSON depending on which prompt it is handed."""

    def complete(self, messages: list[ChatMessage]) -> str:
        prompt = messages[-1].content
        if prompt.startswith("Repository:"):
            return json.dumps(
                {
                    "summary": "A small auth demo.",
                    "architecture": ["api.py calls auth.py for authentication"],
                    "confidence": 0.8,
                }
            )
        return json.dumps(
            {
                "summary": "Handles user authentication.",
                "responsibilities": ["Authenticate a user", "Validate credentials"],
                "key_exports": ["authenticate"],
                "role": "authentication",
                "confidence": 0.9,
            }
        )


def _indexed(tmp_path: Path) -> tuple[Settings, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "auth.py").write_text(
        "def authenticate(user):\n    return validate(user)\n\n"
        "def validate(user):\n    return True\n",
        encoding="utf-8",
    )
    (repo / "api.py").write_text(
        "from auth import authenticate\n\n"
        "class Api:\n"
        "    def login(self, user):\n        return authenticate(user)\n",
        encoding="utf-8",
    )
    settings = Settings.for_repository(repo, db_path=tmp_path / "index.db")
    Indexer(settings).index(repo)
    with Database(settings.db_path) as db:
        row = RepositoryStore(db.connection).get_by_path(str(repo.resolve()))
        assert row is not None
        return settings, row.id


def test_builds_file_and_repo_understanding_offline(tmp_path: Path) -> None:
    settings, repo_id = _indexed(tmp_path)
    with Database(settings.db_path) as db:
        conn = db.connection
        report = ComprehensionBuilder(conn, repo_id).build()
        assert report.files_built == 2
        assert report.repo_built

        auth = FileUnderstandingStore(conn).get(repo_id, "auth.py")
        assert auth is not None
        assert auth.source == "aggregate"
        # Responsibilities enumerate the file's top-level symbols.
        joined = " ".join(auth.responsibilities)
        assert "authenticate" in joined and "validate" in joined
        assert "authenticate" in auth.key_exports

        api = FileUnderstandingStore(conn).get(repo_id, "api.py")
        assert api is not None
        # api.py calls auth.py -> collaboration is detected via the call graph.
        assert "auth.py" in api.collaborators

        repo = RepoUnderstandingStore(conn).get(repo_id)
        assert repo is not None
        assert repo.key_modules  # ranked modules
        assert repo.architecture  # how packages fit together


def test_llm_pass_produces_grounded_understanding(tmp_path: Path) -> None:
    settings, repo_id = _indexed(tmp_path)
    with Database(settings.db_path) as db:
        conn = db.connection
        report = ComprehensionBuilder(conn, repo_id).build(
            chat_client=FakeChatClient(), model="test-model"
        )
        assert report.source == "llm"

        auth = FileUnderstandingStore(conn).get(repo_id, "auth.py")
        assert auth is not None
        assert auth.source == "llm"
        assert auth.summary == "Handles user authentication."
        assert "Authenticate a user" in auth.responsibilities
        # Collaborators stay deterministic (facts), not model-invented.
        api = FileUnderstandingStore(conn).get(repo_id, "api.py")
        assert api is not None and "auth.py" in api.collaborators

        repo = RepoUnderstandingStore(conn).get(repo_id)
        assert repo is not None
        assert repo.source == "llm"
        assert repo.summary == "A small auth demo."
        assert repo.entry_points is not None  # deterministic entry points preserved


def test_llm_failure_degrades_to_aggregate(tmp_path: Path) -> None:
    class Rambling:
        def complete(self, messages: list[ChatMessage]) -> str:
            return "no json here"

    settings, repo_id = _indexed(tmp_path)
    with Database(settings.db_path) as db:
        conn = db.connection
        report = ComprehensionBuilder(conn, repo_id).build(chat_client=Rambling())
        assert report.source == "aggregate"  # no LLM output survived
        auth = FileUnderstandingStore(conn).get(repo_id, "auth.py")
        assert auth is not None and auth.source == "aggregate"


def test_rebuild_is_incremental(tmp_path: Path) -> None:
    settings, repo_id = _indexed(tmp_path)
    with Database(settings.db_path) as db:
        conn = db.connection
        ComprehensionBuilder(conn, repo_id).build()
        # Nothing changed -> a second build skips every file.
        again = ComprehensionBuilder(conn, repo_id).build()
        assert again.files_built == 0
        assert again.files_skipped == 2
        # force rebuilds everything.
        forced = ComprehensionBuilder(conn, repo_id).build(force=True)
        assert forced.files_built == 2
