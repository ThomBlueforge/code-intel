"""Tests for language detection."""

from __future__ import annotations

from pathlib import Path

import pytest

from code_intel.ingestion.languages import detect_language, supported_languages


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("main.py", "Python"),
        ("component.tsx", "TypeScript"),
        ("script.js", "JavaScript"),
        ("server.go", "Go"),
        ("lib.rs", "Rust"),
        ("App.java", "Java"),
        ("Program.cs", "C#"),
        ("index.php", "PHP"),
        ("View.swift", "Swift"),
        ("Main.kt", "Kotlin"),
        ("core.c", "C"),
        ("engine.cpp", "C++"),
        ("schema.sql", "SQL"),
        ("page.html", "HTML"),
        ("style.css", "CSS"),
        ("README.md", "Markdown"),
        ("config.yaml", "YAML"),
        ("data.json", "JSON"),
    ],
)
def test_detects_known_extensions(filename: str, expected: str) -> None:
    assert detect_language(Path(filename)) == expected


def test_returns_none_for_unknown_extension() -> None:
    assert detect_language(Path("notes.xyz")) is None


def test_detects_extensionless_special_filenames() -> None:
    assert detect_language(Path("Dockerfile")) == "Dockerfile"
    assert detect_language(Path("Makefile")) == "Makefile"


def test_supported_languages_covers_required_set() -> None:
    required = {
        "Python", "TypeScript", "JavaScript", "Go", "Rust", "Java", "C#",
        "PHP", "Swift", "Kotlin", "C", "C++", "SQL", "HTML", "CSS",
        "Markdown", "YAML", "JSON",
    }
    assert required.issubset(supported_languages())
