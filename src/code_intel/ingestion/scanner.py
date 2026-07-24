"""Recursive repository scanner.

Streams eligible files as ``ScannedFile`` records. Filtering order, cheapest
first: ignored directory names, then .gitignore rules, then language detection,
then size/binary probing. Streaming (a generator) keeps memory flat on large
repositories, which Phase 18 depends on.

Known limitation: only the repository-root ``.gitignore`` and
``.git/info/exclude`` are honoured. Nested per-directory ``.gitignore`` files
are not yet parsed (documented in PHASE_1.md).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pathspec

from code_intel.config import ScanSettings
from code_intel.ingestion.hashing import probe_file
from code_intel.ingestion.languages import detect_language

# Minified/generated bundles carry no meaningful symbols; skip them by name so
# vendored `*.min.js` outside an ignored directory doesn't reach the parser.
_GENERATED_SUFFIXES = (".min.js", ".min.mjs", ".min.cjs", ".min.css", ".bundle.js")


@dataclass(frozen=True)
class ScannedFile:
    """An eligible file discovered during a scan."""

    rel_path: str  # repository-relative, POSIX-normalised
    abs_path: Path
    language: str
    size_bytes: int
    mtime: float
    hash: str


@dataclass(frozen=True)
class ScanCounters:
    """Aggregate counts for observability."""

    skipped_ignored: int = 0
    skipped_unknown_language: int = 0
    skipped_binary: int = 0
    skipped_too_large: int = 0


class Scanner:
    """Walks a repository root and yields eligible files."""

    def __init__(self, settings: ScanSettings) -> None:
        self._settings = settings
        self.counters = ScanCounters()

    def scan(self, root: Path) -> Iterator[ScannedFile]:
        """Yield eligible files under ``root``. Resets counters per call."""
        root = root.resolve()
        self.counters = ScanCounters()
        spec = self._load_gitignore(root) if self._settings.respect_gitignore else None

        for dirpath, dirnames, filenames in os.walk(root):
            current = Path(dirpath)
            # Prune ignored directories in place so os.walk skips them entirely.
            dirnames[:] = [d for d in dirnames if not self._is_ignored_dir(current, d, root, spec)]
            for filename in filenames:
                abs_path = current / filename
                yielded = self._consider_file(abs_path, root, spec)
                if yielded is not None:
                    yield yielded

    def _consider_file(
        self, abs_path: Path, root: Path, spec: pathspec.PathSpec[Any] | None
    ) -> ScannedFile | None:
        rel = abs_path.relative_to(root).as_posix()
        if spec is not None and spec.match_file(rel):
            self._bump("skipped_ignored")
            return None

        if abs_path.name.endswith(_GENERATED_SUFFIXES):
            self._bump("skipped_ignored")
            return None

        language = detect_language(abs_path)
        if language is None:
            self._bump("skipped_unknown_language")
            return None

        try:
            probe = probe_file(abs_path, self._settings.max_file_bytes)
        except OSError:
            # Unreadable (broken symlink, permissions) — treat as absent.
            self._bump("skipped_ignored")
            return None

        if probe.hash is None:
            self._bump("skipped_too_large" if not probe.is_binary else "skipped_binary")
            return None

        return ScannedFile(
            rel_path=rel,
            abs_path=abs_path,
            language=language,
            size_bytes=probe.size_bytes,
            mtime=abs_path.stat().st_mtime,
            hash=probe.hash,
        )

    def _is_ignored_dir(
        self, parent: Path, name: str, root: Path, spec: pathspec.PathSpec[Any] | None
    ) -> bool:
        if name in self._settings.ignored_dirs:
            return True
        if spec is None:
            return False
        rel = (parent / name).relative_to(root).as_posix()
        # Match with a trailing slash so directory-only gitignore rules apply.
        return spec.match_file(rel + "/")

    def _load_gitignore(self, root: Path) -> pathspec.PathSpec[Any] | None:
        patterns: list[str] = []
        for candidate in (root / ".gitignore", root / ".git" / "info" / "exclude"):
            if candidate.is_file():
                patterns.extend(candidate.read_text(encoding="utf-8", errors="ignore").splitlines())
        if not patterns:
            return None
        return pathspec.PathSpec.from_lines("gitignore", patterns)

    def _bump(self, field: str) -> None:
        current = getattr(self.counters, field)
        self.counters = _replace_counter(self.counters, field, current + 1)


def _replace_counter(counters: ScanCounters, field: str, value: int) -> ScanCounters:
    values = {
        "skipped_ignored": counters.skipped_ignored,
        "skipped_unknown_language": counters.skipped_unknown_language,
        "skipped_binary": counters.skipped_binary,
        "skipped_too_large": counters.skipped_too_large,
    }
    values[field] = value
    return ScanCounters(**values)
