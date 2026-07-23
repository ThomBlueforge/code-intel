"""Tests for the recursive scanner."""

from __future__ import annotations

from pathlib import Path

from code_intel.config import ScanSettings
from code_intel.ingestion.scanner import Scanner


def _scan_paths(root: Path) -> set[str]:
    scanner = Scanner(ScanSettings())
    return {f.rel_path for f in scanner.scan(root)}


def test_includes_known_source_files(sample_repo: Path) -> None:
    paths = _scan_paths(sample_repo)
    assert "src/main.py" in paths
    assert "src/app.ts" in paths
    assert "README.md" in paths
    assert "query.sql" in paths


def test_respects_gitignore(sample_repo: Path) -> None:
    paths = _scan_paths(sample_repo)
    assert "secret.py" not in paths
    assert "dist/bundle.js" not in paths


def test_skips_always_ignored_dirs(sample_repo: Path) -> None:
    paths = _scan_paths(sample_repo)
    assert not any(p.startswith("node_modules/") for p in paths)


def test_skips_unknown_extension_and_binary(sample_repo: Path) -> None:
    paths = _scan_paths(sample_repo)
    assert "notes.xyz" not in paths
    assert "image.png" not in paths
    assert "corrupt.js" not in paths  # binary content, recognised extension


def test_counters_track_skips(sample_repo: Path) -> None:
    scanner = Scanner(ScanSettings())
    list(scanner.scan(sample_repo))
    assert scanner.counters.skipped_unknown_language >= 1  # notes.xyz
    assert scanner.counters.skipped_binary >= 1  # image.png


def test_can_disable_gitignore(sample_repo: Path) -> None:
    scanner = Scanner(ScanSettings(respect_gitignore=False))
    paths = {f.rel_path for f in scanner.scan(sample_repo)}
    assert "secret.py" in paths  # no longer filtered
