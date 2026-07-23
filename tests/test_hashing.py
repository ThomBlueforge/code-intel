"""Tests for content hashing and binary detection."""

from __future__ import annotations

from pathlib import Path

from code_intel.ingestion.hashing import probe_file


def test_hashes_text_file(tmp_path: Path) -> None:
    f = tmp_path / "a.py"
    f.write_text("print('hi')\n", encoding="utf-8")
    probe = probe_file(f, max_bytes=1_000_000)
    assert probe.is_binary is False
    assert probe.hash is not None
    assert probe.size_bytes == f.stat().st_size


def test_identical_content_hashes_equal(tmp_path: Path) -> None:
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_text("x = 1\n", encoding="utf-8")
    b.write_text("x = 1\n", encoding="utf-8")
    assert probe_file(a, 1_000_000).hash == probe_file(b, 1_000_000).hash


def test_different_content_hashes_differ(tmp_path: Path) -> None:
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_text("x = 1\n", encoding="utf-8")
    b.write_text("x = 2\n", encoding="utf-8")
    assert probe_file(a, 1_000_000).hash != probe_file(b, 1_000_000).hash


def test_binary_file_is_skipped(tmp_path: Path) -> None:
    f = tmp_path / "image.png"
    f.write_bytes(b"\x89PNG\x00\x00\x00")
    probe = probe_file(f, max_bytes=1_000_000)
    assert probe.is_binary is True
    assert probe.hash is None


def test_oversized_file_is_skipped(tmp_path: Path) -> None:
    f = tmp_path / "big.py"
    f.write_text("a" * 100, encoding="utf-8")
    probe = probe_file(f, max_bytes=10)
    assert probe.hash is None
    assert probe.is_binary is False
    assert probe.size_bytes == 100
