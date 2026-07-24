"""Deterministic answers to structural questions about a repository.

Some questions are about the *shape* of the codebase — "what is the biggest
file?", "what is the longest function?", "where is the retrieval logic?" — and
are answered exactly from the deterministic symbol table, with no LLM and no
retrieval guesswork. :class:`QuestionAnswerer` consults this first; a match short
-circuits to a factual answer, otherwise the question falls through to grounded
retrieval. All answers here are STATIC_ANALYSIS facts.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

_TOP = 5  # how many results to list for a superlative question

# Words that signal "which is the biggest?" and the noun they target.
_SUPERLATIVES = ("biggest", "largest", "longest", "greatest", "larger", "longer")
_FILE_WORDS = ("file", "module")
_CLASS_WORDS = ("class", "struct", "interface")
_FUNCTION_WORDS = ("function", "method", "def ")

# Words that signal "where does X live?".
_LOCATION_WORDS = (
    "where is",
    "where's",
    "where are",
    "where does",
    "located",
    "location of",
    "defined",
    "definition of",
    "implemented",
    "logic of",
    "logic for",
    "locate",
    "find the",
)

# Noise words never treated as a symbol/name to locate.
_STOPWORDS = frozenset(
    {
        "where", "is", "are", "the", "logic", "of", "for", "a", "an", "in", "on",
        "this", "that", "code", "repo", "repository", "function", "method", "class",
        "located", "location", "find", "defined", "definition", "does", "do", "how",
        "what", "which", "and", "or", "to", "handled", "handle", "implemented",
        "implement", "live", "lives", "reside", "resides", "part", "there", "it",
    }
)
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")


@dataclass(frozen=True)
class StructuralAnswer:
    """A factual answer plus citations, in the same shape the Q&A layer uses."""

    text: str
    citations: list[str]


class StructuralAnswerer:
    """Answers superlative and location questions straight from the symbol table."""

    def __init__(self, conn: sqlite3.Connection, repository_id: str) -> None:
        self._conn = conn
        self._repo_id = repository_id

    def try_answer(self, question: str) -> StructuralAnswer | None:
        q = question.lower()
        if _is_superlative(q):
            if _has(q, _FILE_WORDS):
                return self._biggest_files()
            if _has(q, _CLASS_WORDS):
                return self._biggest_symbols(_CLASS_WORDS, "classes")
            if _has(q, _FUNCTION_WORDS):
                return self._biggest_symbols(("function", "method"), "functions")
            if "symbol" in q or "unit" in q:
                return self._biggest_symbols(None, "symbols")
        if _has(q, _LOCATION_WORDS):
            return self._locate(question)
        return None

    def _biggest_symbols(
        self, types: tuple[str, ...] | None, label: str
    ) -> StructuralAnswer | None:
        sql = (
            "SELECT name, type, path, start_line, end_line, "
            "(end_line - start_line + 1) AS loc "
            "FROM symbols WHERE repository_id = ?"
        )
        params: list[object] = [self._repo_id]
        if types is not None:
            sql += f" AND type IN ({','.join('?' * len(types))})"
            params.extend(types)
        sql += " ORDER BY loc DESC, path ASC LIMIT ?"
        params.append(_TOP)
        rows = self._conn.execute(sql, params).fetchall()
        if not rows:
            return None
        lines = [f"Largest {label} by lines of code (static analysis):"]
        citations: list[str] = []
        for i, r in enumerate(rows):
            lines.append(
                f"  [{i + 1}] {r['name']} — {r['loc']} lines "
                f"({r['path']}:{r['start_line']}–{r['end_line']}) [{r['type']}]"
            )
            citations.append(f"[{i + 1}] {r['path']}:{r['start_line']} {r['type']} {r['name']}")
        return StructuralAnswer("\n".join(lines), citations)

    def _biggest_files(self) -> StructuralAnswer | None:
        rows = self._conn.execute(
            "SELECT path, MAX(end_line) AS lines, COUNT(*) AS symbols "
            "FROM symbols WHERE repository_id = ? "
            "GROUP BY path ORDER BY lines DESC, path ASC LIMIT ?",
            (self._repo_id, _TOP),
        ).fetchall()
        if not rows:
            return None
        lines = ["Largest files by lines of code (static analysis):"]
        citations: list[str] = []
        for i, r in enumerate(rows):
            lines.append(
                f"  [{i + 1}] {r['path']} — ~{r['lines']} lines, {r['symbols']} symbols"
            )
            citations.append(f"[{i + 1}] {r['path']}:1")
        return StructuralAnswer("\n".join(lines), citations)

    def _locate(self, question: str) -> StructuralAnswer | None:
        candidates = [
            w for w in _WORD.findall(question) if w.lower() not in _STOPWORDS
        ]
        if not candidates:
            return None
        seen: set[str] = set()
        found: list[sqlite3.Row] = []
        for cand in candidates:
            like = f"%{cand}%"
            rows = self._conn.execute(
                "SELECT DISTINCT name, type, path, start_line, end_line FROM symbols "
                "WHERE repository_id = ? AND (name LIKE ? OR path LIKE ?) "
                "ORDER BY (end_line - start_line) DESC LIMIT ?",
                (self._repo_id, like, like, _TOP),
            ).fetchall()
            for r in rows:
                key = f"{r['path']}:{r['start_line']}:{r['name']}"
                if key not in seen:
                    seen.add(key)
                    found.append(r)
        if not found:
            return None
        found = found[: _TOP * 2]
        lines = ["Matching definitions (static analysis):"]
        citations: list[str] = []
        for i, r in enumerate(found):
            lines.append(
                f"  [{i + 1}] {r['type']} {r['name']} — {r['path']}:{r['start_line']}"
            )
            citations.append(f"[{i + 1}] {r['path']}:{r['start_line']} {r['type']} {r['name']}")
        return StructuralAnswer("\n".join(lines), citations)


def _is_superlative(q: str) -> bool:
    return any(w in q for w in _SUPERLATIVES) or "most lines" in q or "how big" in q


def _has(q: str, words: tuple[str, ...]) -> bool:
    return any(w in q for w in words)
