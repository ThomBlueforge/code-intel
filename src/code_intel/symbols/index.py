"""Symbol search.

Ranked exact / prefix / substring / fuzzy matching. Candidate rows (minus the
heavy ``code`` column) are filtered in SQL, then scored in Python. Fuzzy scoring
uses the stdlib ``difflib`` ratio so there is no extra dependency. For typical
repositories this stays well under the 200 ms target; on very large repos the
candidate set can be narrowed with the ``languages``/``types``/``path_prefix``
filters, which are pushed into SQL.
"""

from __future__ import annotations

import difflib
import sqlite3
from dataclasses import dataclass

# Below this score, a fuzzy/substring hit is considered noise and dropped.
_MIN_FUZZY_SCORE = 0.45


@dataclass(frozen=True)
class SymbolHit:
    """A lightweight, ranked search result (no source code payload)."""

    id: str
    name: str
    type: str
    language: str
    path: str
    visibility: str
    start_line: int
    end_line: int
    score: float
    match_type: str  # exact | prefix | substring | fuzzy


class SymbolIndex:
    """Searches the deterministic symbol table."""

    _COLUMNS = "id, name, type, language, path, visibility, start_line, end_line"

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def search(
        self,
        repository_id: str,
        query: str,
        *,
        languages: list[str] | None = None,
        types: list[str] | None = None,
        path_prefix: str | None = None,
        limit: int = 20,
    ) -> list[SymbolHit]:
        query = query.strip()
        if not query:
            return []

        rows = self._candidates(repository_id, languages, types, path_prefix)
        scored: list[SymbolHit] = []
        for row in rows:
            score, match_type = _score(row["name"], query)
            if match_type == "fuzzy" and score < _MIN_FUZZY_SCORE:
                continue
            scored.append(_row_to_hit(row, score, match_type))

        scored.sort(key=lambda h: (-h.score, len(h.name), h.path, h.start_line))
        return scored[:limit]

    def _candidates(
        self,
        repository_id: str,
        languages: list[str] | None,
        types: list[str] | None,
        path_prefix: str | None,
    ) -> list[sqlite3.Row]:
        clauses = ["repository_id = ?"]
        params: list[object] = [repository_id]
        if languages:
            clauses.append(f"language IN ({_placeholders(languages)})")
            params.extend(languages)
        if types:
            clauses.append(f"type IN ({_placeholders(types)})")
            params.extend(types)
        if path_prefix:
            clauses.append("path LIKE ?")
            params.append(f"{path_prefix}%")
        where = " AND ".join(clauses)
        return self._conn.execute(
            f"SELECT {self._COLUMNS} FROM symbols WHERE {where}", params
        ).fetchall()


def _placeholders(values: list[str]) -> str:
    return ", ".join("?" for _ in values)


def _score(name: str, query: str) -> tuple[float, str]:
    lowered = name.lower()
    q = query.lower()
    if lowered == q:
        return 1.0, "exact"
    if lowered.startswith(q):
        # Closer length to the query ranks higher.
        penalty = (len(lowered) - len(q)) / max(len(lowered), 1)
        return 0.9 - 0.1 * penalty, "prefix"
    ratio = difflib.SequenceMatcher(None, q, lowered).ratio()
    if q in lowered:
        return max(ratio, 0.7), "substring"
    return ratio, "fuzzy"


def _row_to_hit(row: sqlite3.Row, score: float, match_type: str) -> SymbolHit:
    return SymbolHit(
        id=row["id"],
        name=row["name"],
        type=row["type"],
        language=row["language"],
        path=row["path"],
        visibility=row["visibility"],
        start_line=row["start_line"],
        end_line=row["end_line"],
        score=round(score, 4),
        match_type=match_type,
    )
