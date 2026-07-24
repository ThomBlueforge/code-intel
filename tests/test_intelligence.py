"""Tests for repository intelligence and pattern detection (Phases 13 & 21)."""

from __future__ import annotations

from pathlib import Path

from code_intel.config import Settings
from code_intel.ingestion.indexer import Indexer
from code_intel.intelligence.patterns import PatternDetector
from code_intel.intelligence.report import IntelligenceEngine
from code_intel.storage.database import Database
from code_intel.storage.repositories import FindingStore, RepositoryStore


def _analyze(tmp_path: Path, files: dict[str, str]):
    repo = tmp_path / "repo"
    repo.mkdir()
    for rel, content in files.items():
        (repo / rel).write_text(content, encoding="utf-8")
    settings = Settings.for_repository(repo, db_path=tmp_path / "index.db")
    Indexer(settings).index(repo)
    with Database(settings.db_path) as db:
        conn = db.connection
        repo_row = RepositoryStore(conn).get_by_path(str(repo.resolve()))
        assert repo_row is not None
        report = IntelligenceEngine(conn, repo.resolve()).analyze(repo_row.id)
        return settings, repo_row.id, report


def test_detects_duplicate_and_dead_code(tmp_path: Path) -> None:
    body = "def {n}():\n    a = 1\n    b = 2\n    c = 3\n    return a + b + c\n"
    _s, _r, report = _analyze(
        tmp_path,
        {
            "a.py": body.format(n="alpha") + "\ndef orphan():\n    return 99\n",
            "b.py": body.format(n="alpha"),
        },
    )
    categories = {f.category for f in report.findings}
    assert "duplicate_logic" in categories
    assert "dead_code" in categories


def test_detects_repository_pattern_and_god_object(tmp_path: Path) -> None:
    # Data-access method names so the class matches the Repository pattern
    # structurally, not just by name.
    methods = "".join(f"    def get{i}(self):\n        return {i}\n" for i in range(16))
    _s, _r, report = _analyze(
        tmp_path,
        {
            "stores.py": f"class UserRepository:\n{methods}",
        },
    )
    categories = {f.category for f in report.findings}
    assert "design_pattern" in categories  # UserRepository -> Repository
    assert "god_object" in categories  # 16 methods


def test_named_like_pattern_without_methods_is_not_flagged(tmp_path: Path) -> None:
    # A data model merely named `Repository` (no data-access methods) is not the
    # Repository pattern and must not be reported.
    _s, _r, report = _analyze(
        tmp_path,
        {"models.py": "class Repository:\n    id: str\n    path: str\n    name: str\n"},
    )
    assert not any(f.category == "design_pattern" for f in report.findings)


def test_findings_carry_origin_and_confidence(tmp_path: Path) -> None:
    src = "def f():\n    return g()\ndef g():\n    return 1\n"
    _s, _r, report = _analyze(tmp_path, {"a.py": src})
    assert all(f.origin in ("STATIC_ANALYSIS", "LLM_INFERENCE") for f in report.findings)
    assert all(0.0 <= f.confidence <= 1.0 for f in report.findings)


def test_findings_persisted_and_diffable(tmp_path: Path) -> None:
    settings, repo_id, report = _analyze(
        tmp_path, {"a.py": "def orphan():\n    return 1\n"}
    )
    with Database(settings.db_path) as db:
        conn = db.connection
        store = FindingStore(conn)
        store.replace_all(repo_id, report.findings)
        conn.commit()
        stored = store.list_for_repository(repo_id)
    assert len(stored) == len(report.findings)
    # A second identical run yields the same finding keys (diffable, stable).
    keys_1 = {(f.category, f.target) for f in report.findings}
    with Database(settings.db_path) as db:
        again = IntelligenceEngine(db.connection, settings.db_path.parent / "repo").analyze(
            repo_id
        )
    keys_2 = {(f.category, f.target) for f in again.findings}
    assert keys_1 == keys_2


def test_pattern_detector_directly() -> None:
    from code_intel.models import Symbol

    def sym(sid: str, name: str, type_: str, parent: str | None, lines: int) -> Symbol:
        return Symbol(
            id=sid, repository_id="r", file_id="f", name=name, type=type_, language="Python",
            path="p.py", start_line=1, end_line=lines, signature="", visibility="public",
            parent_id=parent, code="", hash="h", created_at="t", updated_at="t",
        )

    cls = sym("c", "OrderFactory", "class", None, 10)
    children = {
        "c": [
            sym("m0", "create", "method", "c", 2),  # factory method -> structural match
            sym("m1", "helper", "method", "c", 2),
        ]
    }
    found = PatternDetector().detect([cls], children)
    assert any(p.category == "design_pattern" and "Factory" in p.title for p in found)
