"""Keyword search over indexed files.

``KeywordSearcher`` picks a ripgrep backend when the binary is resolvable and a
pure-Python backend otherwise; both return identical ``KeywordMatch`` shapes.
Context lines are always assembled from the file so the two backends agree.
Search is restricted to the indexed file manifest (and optionally to given
languages).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from code_intel.models import FileRecord

_DEFAULT_CONTEXT = 2
_DEFAULT_LIMIT = 100


@dataclass(frozen=True)
class KeywordMatch:
    """A single matching line with surrounding context."""

    path: str
    line_number: int  # 1-based
    line: str
    before: list[str]
    after: list[str]


class KeywordSearcher:
    """Searches indexed files for a keyword or regex."""

    def __init__(
        self,
        repo_path: Path,
        files: list[FileRecord],
        ripgrep_path: str | None = None,
    ) -> None:
        self._repo_path = repo_path
        self._files = files
        self._ripgrep = ripgrep_path or shutil.which("rg")

    @property
    def backend_name(self) -> str:
        return "ripgrep" if self._ripgrep else "python"

    def search(
        self,
        text: str,
        *,
        regex: bool = False,
        case_sensitive: bool = False,
        languages: list[str] | None = None,
        context: int = _DEFAULT_CONTEXT,
        limit: int = _DEFAULT_LIMIT,
    ) -> list[KeywordMatch]:
        if not text:
            return []
        allowed = self._allowed_files(languages)
        if self._ripgrep:
            hit_lines = self._ripgrep_hits(text, regex, case_sensitive, allowed)
        else:
            hit_lines = self._python_hits(text, regex, case_sensitive, allowed, limit)
        return self._assemble(hit_lines, context, limit)

    def _allowed_files(self, languages: list[str] | None) -> dict[str, FileRecord]:
        wanted = set(languages) if languages else None
        return {
            f.path: f for f in self._files if wanted is None or f.language in wanted
        }

    def _python_hits(
        self,
        text: str,
        regex: bool,
        case_sensitive: bool,
        allowed: dict[str, FileRecord],
        limit: int,
    ) -> list[tuple[str, int]]:
        pattern = _compile(text, regex, case_sensitive)
        hits: list[tuple[str, int]] = []
        for rel_path in allowed:
            lines = self._read_lines(rel_path)
            for index, line in enumerate(lines):
                if pattern.search(line):
                    hits.append((rel_path, index + 1))
                    if len(hits) >= limit:
                        return hits
        return hits

    def _ripgrep_hits(
        self,
        text: str,
        regex: bool,
        case_sensitive: bool,
        allowed: dict[str, FileRecord],
    ) -> list[tuple[str, int]]:
        args = [self._ripgrep or "rg", "--json", "--line-number", "--no-heading"]
        if not case_sensitive:
            args.append("--ignore-case")
        if not regex:
            args.append("--fixed-strings")
        args.extend([text, str(self._repo_path)])
        try:
            proc = subprocess.run(  # noqa: S603 - args are controlled
                args, capture_output=True, text=True, timeout=30, check=False
            )
        except (OSError, subprocess.SubprocessError):
            return []
        hits: list[tuple[str, int]] = []
        for raw in proc.stdout.splitlines():
            parsed = _parse_rg_line(raw, self._repo_path)
            if parsed is not None and parsed[0] in allowed:
                hits.append(parsed)
        return hits

    def _assemble(
        self, hit_lines: list[tuple[str, int]], context: int, limit: int
    ) -> list[KeywordMatch]:
        by_file: dict[str, list[str]] = {}
        matches: list[KeywordMatch] = []
        for rel_path, line_number in hit_lines[:limit]:
            if rel_path not in by_file:
                by_file[rel_path] = self._read_lines(rel_path)
            lines = by_file[rel_path]
            index = line_number - 1
            if index < 0 or index >= len(lines):
                continue
            matches.append(
                KeywordMatch(
                    path=rel_path,
                    line_number=line_number,
                    line=lines[index],
                    before=lines[max(0, index - context) : index],
                    after=lines[index + 1 : index + 1 + context],
                )
            )
        return matches

    def _read_lines(self, rel_path: str) -> list[str]:
        try:
            return (self._repo_path / rel_path).read_text(
                encoding="utf-8", errors="replace"
            ).splitlines()
        except OSError:
            return []


def _compile(text: str, regex: bool, case_sensitive: bool) -> re.Pattern[str]:
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(text if regex else re.escape(text), flags)


def _parse_rg_line(raw: str, repo_path: Path) -> tuple[str, int] | None:
    try:
        event = json.loads(raw)
    except ValueError:
        return None
    if event.get("type") != "match":
        return None
    data = event.get("data", {})
    absolute = data.get("path", {}).get("text")
    line_number = data.get("line_number")
    if not absolute or not isinstance(line_number, int):
        return None
    try:
        rel = str(Path(absolute).resolve().relative_to(repo_path.resolve()))
    except ValueError:
        return None
    return rel.replace("\\", "/"), line_number
