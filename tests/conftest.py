"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    """Create a small, realistic repository tree under a temp directory.

    Contains: recognised source files across languages, a file to be ignored by
    .gitignore, a file inside an always-ignored directory, an unknown-extension
    file, and a binary file. Returns the repository root.
    """
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def main():\n    return 1\n", encoding="utf-8")
    (tmp_path / "src" / "app.ts").write_text("export const x = 1;\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Sample\n", encoding="utf-8")
    (tmp_path / "query.sql").write_text("SELECT 1;\n", encoding="utf-8")

    # Ignored by .gitignore
    (tmp_path / ".gitignore").write_text("secret.py\ndist/\n", encoding="utf-8")
    (tmp_path / "secret.py").write_text("KEY = 'x'\n", encoding="utf-8")
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "bundle.js").write_text("console.log(1)\n", encoding="utf-8")

    # Always-ignored directory (node_modules) even without gitignore rule
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "lib.js").write_text("module.exports = {}\n", encoding="utf-8")

    # Unknown extension -> skipped
    (tmp_path / "notes.xyz").write_text("not a known language\n", encoding="utf-8")

    # Binary file with an unknown extension -> skipped as unknown language.
    (tmp_path / "image.png").write_bytes(b"\x89PNG\x00\x00binary\x00data")

    # Binary content behind a recognised code extension -> skipped as binary.
    (tmp_path / "corrupt.js").write_bytes(b"var x=1;\x00\x00garbage\x00")

    return tmp_path
