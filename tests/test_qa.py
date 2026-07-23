"""Tests for grounded question answering (Phase 12)."""

from __future__ import annotations

from pathlib import Path

from code_intel.config import Settings
from code_intel.ingestion.indexer import Indexer
from code_intel.llm.client import ChatMessage
from code_intel.retrieval.hybrid import HybridRetriever
from code_intel.storage.database import Database
from code_intel.storage.repositories import RepositoryStore
from code_intel.understanding.qa import QuestionAnswerer


class RecordingChatClient:
    """Returns a canned answer and records the context it was given."""

    def __init__(self) -> None:
        self.last_prompt = ""

    def complete(self, messages: list[ChatMessage]) -> str:
        self.last_prompt = messages[-1].content
        return "Authentication is handled by authenticate() [1]."


def _indexed(tmp_path: Path) -> tuple[Settings, str, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "auth.py").write_text(
        "def authenticate(user):\n    return validate(user)\n\n"
        "def validate(user):\n    return True\n",
        encoding="utf-8",
    )
    settings = Settings.for_repository(repo, db_path=tmp_path / "index.db")
    Indexer(settings).index(repo)
    with Database(settings.db_path) as db:
        row = RepositoryStore(db.connection).get_by_path(str(repo.resolve()))
        assert row is not None
        return settings, row.id, repo


def test_ask_with_llm_returns_answer_and_citations(tmp_path: Path) -> None:
    settings, repo_id, repo = _indexed(tmp_path)
    client = RecordingChatClient()
    with Database(settings.db_path) as db:
        conn = db.connection
        retriever = HybridRetriever(conn, repo_id, repo)
        answer = QuestionAnswerer(conn, repo_id, retriever, chat_client=client).ask(
            "How does authentication work?"
        )
    assert answer.used_llm is True
    assert "authenticate" in answer.answer
    assert answer.citations
    # The LLM only ever saw assembled context, never the raw repo.
    assert "authenticate" in client.last_prompt
    assert "code:" in client.last_prompt


def test_ask_without_llm_degrades_to_cited_context(tmp_path: Path) -> None:
    settings, repo_id, repo = _indexed(tmp_path)
    with Database(settings.db_path) as db:
        conn = db.connection
        retriever = HybridRetriever(conn, repo_id, repo)
        answer = QuestionAnswerer(conn, repo_id, retriever, chat_client=None).ask(
            "authenticate"
        )
    assert answer.used_llm is False
    assert answer.citations
    assert "authenticate" in answer.answer


def test_ask_no_results(tmp_path: Path) -> None:
    settings, repo_id, repo = _indexed(tmp_path)
    with Database(settings.db_path) as db:
        conn = db.connection
        retriever = HybridRetriever(conn, repo_id, repo)
        answer = QuestionAnswerer(conn, repo_id, retriever).ask("zzznonexistentquery")
    assert answer.citations == []
