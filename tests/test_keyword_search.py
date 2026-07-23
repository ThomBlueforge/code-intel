"""Tests for keyword search (Python backend; ripgrep path exercised if present)."""

from __future__ import annotations

from pathlib import Path

from code_intel.keyword_search.searcher import KeywordSearcher
from code_intel.models import FileRecord


def _file(path: str, language: str) -> FileRecord:
    return FileRecord(
        id=path,
        repository_id="r",
        path=path,
        language=language,
        hash="h",
        size_bytes=0,
        mtime=0.0,
        created_at="t",
        updated_at="t",
    )


def _repo(tmp_path: Path, files: dict[str, tuple[str, str]]) -> KeywordSearcher:
    records = []
    for rel, (content, language) in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        records.append(_file(rel, language))
    # Force the Python backend so behaviour is deterministic in CI.
    return KeywordSearcher(tmp_path, records, ripgrep_path=None)


def test_exact_match_with_line_and_context(tmp_path: Path) -> None:
    searcher = _repo(
        tmp_path,
        {"a.py": ("import os\n\ndef handler():\n    return authenticate()\n", "Python")},
    )
    matches = searcher.search("authenticate", context=1)
    assert len(matches) == 1
    m = matches[0]
    assert m.path == "a.py"
    assert m.line_number == 4
    assert "authenticate" in m.line
    assert m.before == ["def handler():"]


def test_case_insensitive_by_default(tmp_path: Path) -> None:
    searcher = _repo(tmp_path, {"a.py": ("AuthToken = 1\n", "Python")})
    assert searcher.search("authtoken")
    assert not searcher.search("authtoken", case_sensitive=True)


def test_regex_search(tmp_path: Path) -> None:
    searcher = _repo(tmp_path, {"a.py": ("def foo():\n    pass\ndef bar():\n    pass\n", "Python")})
    matches = searcher.search(r"def \w+\(", regex=True)
    assert len(matches) == 2


def test_language_filter(tmp_path: Path) -> None:
    searcher = _repo(
        tmp_path,
        {
            "a.py": ("token = 1\n", "Python"),
            "b.go": ("var token = 1\n", "Go"),
        },
    )
    matches = searcher.search("token", languages=["Go"])
    assert {m.path for m in matches} == {"b.go"}


def test_limit_caps_results(tmp_path: Path) -> None:
    content = "match\n" * 10
    searcher = _repo(tmp_path, {"a.py": (content, "Python")})
    assert len(searcher.search("match", limit=3)) == 3


def test_empty_query_returns_nothing(tmp_path: Path) -> None:
    searcher = _repo(tmp_path, {"a.py": ("x = 1\n", "Python")})
    assert searcher.search("") == []


def test_python_backend_reported(tmp_path: Path) -> None:
    searcher = _repo(tmp_path, {"a.py": ("x = 1\n", "Python")})
    assert searcher.backend_name == "python"
