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


def test_skips_build_output_dir_and_minified_files(tmp_path: Path) -> None:
    # Build output (Next.js `out/`) and minified bundles carry no real symbols.
    (tmp_path / "web" / "out" / "_next").mkdir(parents=True)
    (tmp_path / "web" / "out" / "_next" / "chunk.js").write_text("var s={};", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.js").write_text("export const x = 1;\n", encoding="utf-8")
    (tmp_path / "src" / "vendor.min.js").write_text("!function(){}();", encoding="utf-8")

    paths = _scan_paths(tmp_path)
    assert "src/app.js" in paths  # real source still scanned
    assert not any(p.startswith("web/out/") for p in paths)  # export dir pruned
    assert "src/vendor.min.js" not in paths  # minified bundle skipped by name


def test_can_disable_gitignore(sample_repo: Path) -> None:
    scanner = Scanner(ScanSettings(respect_gitignore=False))
    paths = {f.rel_path for f in scanner.scan(sample_repo)}
    assert "secret.py" in paths  # no longer filtered
