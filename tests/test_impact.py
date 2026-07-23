"""Tests for change-impact analysis (Phase 22)."""

from __future__ import annotations

from pathlib import Path

from code_intel.config import Settings
from code_intel.dependencies.impact import ImpactAnalyzer
from code_intel.ingestion.indexer import Indexer
from code_intel.storage.database import Database
from code_intel.storage.repositories import RepositoryStore, SymbolStore


def _symbols(tmp_path: Path, files: dict[str, str]) -> list:
    repo = tmp_path / "repo"
    repo.mkdir()
    for rel, content in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    settings = Settings.for_repository(repo, db_path=tmp_path / "index.db")
    Indexer(settings).index(repo)
    with Database(settings.db_path) as db:
        conn = db.connection
        repo_row = RepositoryStore(conn).get_by_path(str(repo.resolve()))
        assert repo_row is not None
        return SymbolStore(conn).list_for_repository(repo_row.id)


def test_direct_and_indirect_callers(tmp_path: Path) -> None:
    symbols = _symbols(
        tmp_path,
        {
            "core.py": (
                "def base():\n    return 1\n\n"
                "def middle():\n    return base()\n\n"
                "def top():\n    return middle()\n"
            )
        },
    )
    report = ImpactAnalyzer(symbols).impact("base")
    direct = " ".join(report.direct_callers)
    indirect = " ".join(report.indirect_callers)
    assert "middle" in direct
    assert "top" in indirect  # reaches base only through middle


def test_affected_files_and_tests(tmp_path: Path) -> None:
    symbols = _symbols(
        tmp_path,
        {
            "svc.py": "def process():\n    return 1\n",
            "app.py": "def run():\n    return process()\n",
            "test_svc.py": "def test_process():\n    return process()\n",
        },
    )
    report = ImpactAnalyzer(symbols).impact("process")
    assert "app.py" in report.affected_files
    assert any("test_svc.py" in t for t in report.affected_tests)


def test_unknown_symbol_reports_no_targets(tmp_path: Path) -> None:
    symbols = _symbols(tmp_path, {"a.py": "def f():\n    return 1\n"})
    report = ImpactAnalyzer(symbols).impact("does_not_exist")
    assert report.targets == 0
    assert report.direct_callers == []
