"""Data-access objects (repository pattern) over SQLite.

Business/orchestration code depends on these interfaces, never on raw SQL, so
the storage mechanism can change without touching callers.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass

from code_intel.models import (
    EmbeddingRecord,
    EnrichedSymbol,
    FileRecord,
    FileUnderstanding,
    Finding,
    QualityMetrics,
    Repository,
    RepoUnderstanding,
    Summary,
    Symbol,
    utc_now_iso,
)


@dataclass(frozen=True)
class ManifestEntry:
    """Minimal existing-file view used for incremental diffing."""

    id: str
    hash: str


class RepositoryStore:
    """CRUD for repository roots."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get_by_path(self, path: str) -> Repository | None:
        row = self._conn.execute(
            "SELECT * FROM repositories WHERE path = ?", (path,)
        ).fetchone()
        return _row_to_repository(row) if row else None

    def get_by_id(self, repository_id: str) -> Repository | None:
        row = self._conn.execute(
            "SELECT * FROM repositories WHERE id = ?", (repository_id,)
        ).fetchone()
        return _row_to_repository(row) if row else None

    def get_or_create(self, path: str, name: str) -> Repository:
        existing = self.get_by_path(path)
        if existing is not None:
            return existing
        now = utc_now_iso()
        repo = Repository(
            id=str(uuid.uuid4()), path=path, name=name, created_at=now, updated_at=now
        )
        self._conn.execute(
            "INSERT INTO repositories (id, path, name, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (repo.id, repo.path, repo.name, repo.created_at, repo.updated_at),
        )
        return repo


class FileStore:
    """CRUD and incremental helpers for the file manifest."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def manifest(self, repository_id: str) -> dict[str, ManifestEntry]:
        """Return the current manifest keyed by repository-relative path."""
        rows = self._conn.execute(
            "SELECT path, id, hash FROM files WHERE repository_id = ?",
            (repository_id,),
        ).fetchall()
        return {row["path"]: ManifestEntry(id=row["id"], hash=row["hash"]) for row in rows}

    def count(self, repository_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM files WHERE repository_id = ?", (repository_id,)
        ).fetchone()
        return int(row["n"])

    def insert(self, record: FileRecord) -> None:
        self._conn.execute(
            "INSERT INTO files "
            "(id, repository_id, path, language, hash, size_bytes, mtime, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record.id,
                record.repository_id,
                record.path,
                record.language,
                record.hash,
                record.size_bytes,
                record.mtime,
                record.created_at,
                record.updated_at,
            ),
        )

    def update_content(
        self, file_id: str, *, file_hash: str, size_bytes: int, mtime: float, updated_at: str
    ) -> None:
        self._conn.execute(
            "UPDATE files SET hash = ?, size_bytes = ?, mtime = ?, updated_at = ? WHERE id = ?",
            (file_hash, size_bytes, mtime, updated_at, file_id),
        )

    def delete_many(self, file_ids: list[str]) -> None:
        self._conn.executemany("DELETE FROM files WHERE id = ?", ((fid,) for fid in file_ids))

    def list_records(self, repository_id: str) -> list[FileRecord]:
        rows = self._conn.execute(
            "SELECT * FROM files WHERE repository_id = ? ORDER BY path", (repository_id,)
        ).fetchall()
        return [_row_to_file(row) for row in rows]


class SymbolStore:
    """CRUD for deterministic symbols, keyed to their owning file."""

    _COLUMNS = (
        "id, repository_id, file_id, name, type, language, path, start_line, "
        "end_line, signature, visibility, parent_id, code, hash, created_at, updated_at, "
        "decorators"
    )

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert_many(self, symbols: list[Symbol]) -> None:
        self._conn.executemany(
            f"INSERT INTO symbols ({self._COLUMNS}) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    s.id,
                    s.repository_id,
                    s.file_id,
                    s.name,
                    s.type,
                    s.language,
                    s.path,
                    s.start_line,
                    s.end_line,
                    s.signature,
                    s.visibility,
                    s.parent_id,
                    s.code,
                    s.hash,
                    s.created_at,
                    s.updated_at,
                    ",".join(s.decorators),
                )
                for s in symbols
            ],
        )

    def delete_for_file(self, file_id: str) -> None:
        self._conn.execute("DELETE FROM symbols WHERE file_id = ?", (file_id,))

    def count(self, repository_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM symbols WHERE repository_id = ?", (repository_id,)
        ).fetchone()
        return int(row["n"])

    def list_for_path(self, repository_id: str, path: str) -> list[Symbol]:
        rows = self._conn.execute(
            f"SELECT {self._COLUMNS} FROM symbols WHERE repository_id = ? AND path = ? "
            "ORDER BY start_line",
            (repository_id, path),
        ).fetchall()
        return [_row_to_symbol(row) for row in rows]

    def list_for_repository(self, repository_id: str) -> list[Symbol]:
        rows = self._conn.execute(
            f"SELECT {self._COLUMNS} FROM symbols WHERE repository_id = ? "
            "ORDER BY path, start_line",
            (repository_id,),
        ).fetchall()
        return [_row_to_symbol(row) for row in rows]

    def find_by_name(self, repository_id: str, name: str) -> list[Symbol]:
        rows = self._conn.execute(
            f"SELECT {self._COLUMNS} FROM symbols WHERE repository_id = ? AND name = ? "
            "ORDER BY path, start_line",
            (repository_id, name),
        ).fetchall()
        return [_row_to_symbol(row) for row in rows]


class EnrichedSymbolStore:
    """CRUD for the AI enrichment layer, joinable to symbols by ``symbol_id``.

    Kept strictly separate from deterministic facts: enrichment can be deleted
    and rebuilt without touching symbols, and symbols exist without enrichment.
    """

    _COLUMNS = (
        "symbol_id, summary, business_domain, architecture_layer, responsibilities, "
        "quality_metrics, risks, technical_debt, confidence, model, created_at, updated_at"
    )

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def upsert(self, enriched: EnrichedSymbol) -> None:
        self._conn.execute(
            f"INSERT INTO enriched_symbols ({self._COLUMNS}) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(symbol_id) DO UPDATE SET "
            "summary=excluded.summary, business_domain=excluded.business_domain, "
            "architecture_layer=excluded.architecture_layer, "
            "responsibilities=excluded.responsibilities, "
            "quality_metrics=excluded.quality_metrics, risks=excluded.risks, "
            "technical_debt=excluded.technical_debt, confidence=excluded.confidence, "
            "model=excluded.model, updated_at=excluded.updated_at",
            (
                enriched.symbol_id,
                enriched.summary,
                json.dumps(enriched.business_domain),
                enriched.architecture_layer,
                json.dumps(enriched.responsibilities),
                json.dumps(_metrics_to_dict(enriched.quality_metrics)),
                json.dumps(enriched.risks),
                json.dumps(enriched.technical_debt),
                enriched.confidence,
                enriched.model,
                enriched.created_at,
                enriched.updated_at,
            ),
        )

    def get(self, symbol_id: str) -> EnrichedSymbol | None:
        row = self._conn.execute(
            f"SELECT {self._COLUMNS} FROM enriched_symbols WHERE symbol_id = ?",
            (symbol_id,),
        ).fetchone()
        return _row_to_enriched(row) if row else None

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS n FROM enriched_symbols").fetchone()
        return int(row["n"])

    def enriched_ids(self) -> set[str]:
        rows = self._conn.execute("SELECT symbol_id FROM enriched_symbols").fetchall()
        return {row["symbol_id"] for row in rows}

    def map_for_repository(self, repository_id: str) -> dict[str, EnrichedSymbol]:
        """All enrichment rows for a repo, keyed by ``symbol_id`` (joined via symbols)."""
        rows = self._conn.execute(
            f"SELECT e.{', e.'.join(self._COLUMNS.split(', '))} FROM enriched_symbols e "
            "JOIN symbols s ON s.id = e.symbol_id WHERE s.repository_id = ?",
            (repository_id,),
        ).fetchall()
        return {row["symbol_id"]: _row_to_enriched(row) for row in rows}


class EmbeddingStore:
    """Traceability records for embedded symbols (no vectors)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def upsert(self, record: EmbeddingRecord) -> None:
        self._conn.execute(
            "INSERT INTO embeddings (symbol_id, model, dimension, content_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(symbol_id) DO UPDATE SET model=excluded.model, "
            "dimension=excluded.dimension, content_hash=excluded.content_hash, "
            "created_at=excluded.created_at",
            (
                record.symbol_id,
                record.model,
                record.dimension,
                record.content_hash,
                record.created_at,
            ),
        )

    def get(self, symbol_id: str) -> EmbeddingRecord | None:
        row = self._conn.execute(
            "SELECT symbol_id, model, dimension, content_hash, created_at "
            "FROM embeddings WHERE symbol_id = ?",
            (symbol_id,),
        ).fetchone()
        if row is None:
            return None
        return EmbeddingRecord(
            symbol_id=row["symbol_id"],
            model=row["model"],
            dimension=row["dimension"],
            content_hash=row["content_hash"],
            created_at=row["created_at"],
        )

    def embedded_hashes(self) -> dict[str, str]:
        rows = self._conn.execute("SELECT symbol_id, content_hash FROM embeddings").fetchall()
        return {row["symbol_id"]: row["content_hash"] for row in rows}

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS n FROM embeddings").fetchone()
        return int(row["n"])


class SummaryStore:
    """Hierarchical summaries (repository memory)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def upsert(self, summary: Summary) -> None:
        self._conn.execute(
            "INSERT INTO summaries (scope, target_key, path, summary, source, confidence, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(scope, target_key) DO UPDATE SET summary=excluded.summary, "
            "source=excluded.source, confidence=excluded.confidence, "
            "created_at=excluded.created_at, path=excluded.path",
            (
                summary.scope,
                summary.target_key,
                summary.path,
                summary.summary,
                summary.source,
                summary.confidence,
                summary.created_at,
            ),
        )

    def get(self, scope: str, target_key: str) -> Summary | None:
        row = self._conn.execute(
            "SELECT scope, target_key, path, summary, source, confidence, created_at "
            "FROM summaries WHERE scope = ? AND target_key = ?",
            (scope, target_key),
        ).fetchone()
        return _row_to_summary(row) if row else None

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS n FROM summaries").fetchone()
        return int(row["n"])


class FindingStore:
    """Repository intelligence findings."""

    _COLUMNS = (
        "id, repository_id, category, title, detail, origin, confidence, target, created_at"
    )

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def replace_all(self, repository_id: str, findings: list[Finding]) -> None:
        """Replace the finding set for a repository atomically."""
        self._conn.execute("DELETE FROM findings WHERE repository_id = ?", (repository_id,))
        self._conn.executemany(
            f"INSERT INTO findings ({self._COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    f.id,
                    f.repository_id,
                    f.category,
                    f.title,
                    f.detail,
                    f.origin,
                    f.confidence,
                    f.target,
                    f.created_at,
                )
                for f in findings
            ],
        )

    def list_for_repository(self, repository_id: str) -> list[Finding]:
        rows = self._conn.execute(
            f"SELECT {self._COLUMNS} FROM findings WHERE repository_id = ? "
            "ORDER BY confidence DESC, category",
            (repository_id,),
        ).fetchall()
        return [_row_to_finding(row) for row in rows]


class FileUnderstandingStore:
    """Holistic per-file understanding (Phase 23). List fields are JSON text."""

    _COLUMNS = (
        "repository_id, path, summary, responsibilities, key_exports, collaborators, "
        "role, source, confidence, content_hash, model, created_at, updated_at"
    )

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def upsert(self, fu: FileUnderstanding) -> None:
        self._conn.execute(
            f"INSERT INTO file_understanding ({self._COLUMNS}) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(repository_id, path) DO UPDATE SET "
            "summary=excluded.summary, responsibilities=excluded.responsibilities, "
            "key_exports=excluded.key_exports, collaborators=excluded.collaborators, "
            "role=excluded.role, source=excluded.source, confidence=excluded.confidence, "
            "content_hash=excluded.content_hash, model=excluded.model, "
            "updated_at=excluded.updated_at",
            (
                fu.repository_id,
                fu.path,
                fu.summary,
                json.dumps(fu.responsibilities),
                json.dumps(fu.key_exports),
                json.dumps(fu.collaborators),
                fu.role,
                fu.source,
                fu.confidence,
                fu.content_hash,
                fu.model,
                fu.created_at,
                fu.updated_at,
            ),
        )

    def get(self, repository_id: str, path: str) -> FileUnderstanding | None:
        row = self._conn.execute(
            f"SELECT {self._COLUMNS} FROM file_understanding "
            "WHERE repository_id = ? AND path = ?",
            (repository_id, path),
        ).fetchone()
        return _row_to_file_understanding(row) if row else None

    def map_for_repository(self, repository_id: str) -> dict[str, FileUnderstanding]:
        rows = self._conn.execute(
            f"SELECT {self._COLUMNS} FROM file_understanding WHERE repository_id = ?",
            (repository_id,),
        ).fetchall()
        return {row["path"]: _row_to_file_understanding(row) for row in rows}

    def hashes(self, repository_id: str) -> dict[str, str]:
        """Path -> content_hash, so a rebuild can skip unchanged files."""
        rows = self._conn.execute(
            "SELECT path, content_hash FROM file_understanding WHERE repository_id = ?",
            (repository_id,),
        ).fetchall()
        return {row["path"]: row["content_hash"] for row in rows}

    def count(self, repository_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM file_understanding WHERE repository_id = ?",
            (repository_id,),
        ).fetchone()
        return int(row["n"])


class RepoUnderstandingStore:
    """The single top-level repository overview (Phase 23)."""

    _COLUMNS = (
        "repository_id, summary, architecture, entry_points, key_modules, source, "
        "confidence, content_hash, model, created_at, updated_at"
    )

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def upsert(self, ru: RepoUnderstanding) -> None:
        self._conn.execute(
            f"INSERT INTO repo_understanding ({self._COLUMNS}) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(repository_id) DO UPDATE SET "
            "summary=excluded.summary, architecture=excluded.architecture, "
            "entry_points=excluded.entry_points, key_modules=excluded.key_modules, "
            "source=excluded.source, confidence=excluded.confidence, "
            "content_hash=excluded.content_hash, model=excluded.model, "
            "updated_at=excluded.updated_at",
            (
                ru.repository_id,
                ru.summary,
                json.dumps(ru.architecture),
                json.dumps(ru.entry_points),
                json.dumps(ru.key_modules),
                ru.source,
                ru.confidence,
                ru.content_hash,
                ru.model,
                ru.created_at,
                ru.updated_at,
            ),
        )

    def get(self, repository_id: str) -> RepoUnderstanding | None:
        row = self._conn.execute(
            f"SELECT {self._COLUMNS} FROM repo_understanding WHERE repository_id = ?",
            (repository_id,),
        ).fetchone()
        return _row_to_repo_understanding(row) if row else None


def _row_to_summary(row: sqlite3.Row) -> Summary:
    return Summary(
        scope=row["scope"],
        target_key=row["target_key"],
        path=row["path"],
        summary=row["summary"],
        source=row["source"],
        confidence=row["confidence"],
        created_at=row["created_at"],
    )


def _row_to_finding(row: sqlite3.Row) -> Finding:
    return Finding(
        id=row["id"],
        repository_id=row["repository_id"],
        category=row["category"],
        title=row["title"],
        detail=row["detail"],
        origin=row["origin"],
        confidence=row["confidence"],
        target=row["target"],
        created_at=row["created_at"],
    )


def _metrics_to_dict(metrics: QualityMetrics) -> dict[str, float]:
    return {
        "complexity": metrics.complexity,
        "maintainability": metrics.maintainability,
        "readability": metrics.readability,
        "coupling": metrics.coupling,
        "cohesion": metrics.cohesion,
        "testability": metrics.testability,
        "risk": metrics.risk,
        "stability": metrics.stability,
        "reusability": metrics.reusability,
        "technical_debt": metrics.technical_debt,
    }


def _row_to_enriched(row: sqlite3.Row) -> EnrichedSymbol:
    metrics = json.loads(row["quality_metrics"])
    return EnrichedSymbol(
        symbol_id=row["symbol_id"],
        summary=row["summary"],
        business_domain=json.loads(row["business_domain"]),
        architecture_layer=row["architecture_layer"],
        responsibilities=json.loads(row["responsibilities"]),
        quality_metrics=QualityMetrics(**metrics),
        risks=json.loads(row["risks"]),
        technical_debt=json.loads(row["technical_debt"]),
        confidence=row["confidence"],
        model=row["model"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_symbol(row: sqlite3.Row) -> Symbol:
    return Symbol(
        id=row["id"],
        repository_id=row["repository_id"],
        file_id=row["file_id"],
        name=row["name"],
        type=row["type"],
        language=row["language"],
        path=row["path"],
        start_line=row["start_line"],
        end_line=row["end_line"],
        signature=row["signature"],
        visibility=row["visibility"],
        parent_id=row["parent_id"],
        code=row["code"],
        hash=row["hash"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        decorators=tuple(d for d in (row["decorators"] or "").split(",") if d),
    )


def _row_to_file_understanding(row: sqlite3.Row) -> FileUnderstanding:
    return FileUnderstanding(
        repository_id=row["repository_id"],
        path=row["path"],
        summary=row["summary"],
        responsibilities=json.loads(row["responsibilities"]),
        key_exports=json.loads(row["key_exports"]),
        collaborators=json.loads(row["collaborators"]),
        role=row["role"],
        source=row["source"],
        confidence=row["confidence"],
        content_hash=row["content_hash"],
        model=row["model"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_repo_understanding(row: sqlite3.Row) -> RepoUnderstanding:
    return RepoUnderstanding(
        repository_id=row["repository_id"],
        summary=row["summary"],
        architecture=json.loads(row["architecture"]),
        entry_points=json.loads(row["entry_points"]),
        key_modules=json.loads(row["key_modules"]),
        source=row["source"],
        confidence=row["confidence"],
        content_hash=row["content_hash"],
        model=row["model"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_repository(row: sqlite3.Row) -> Repository:
    return Repository(
        id=row["id"],
        path=row["path"],
        name=row["name"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_file(row: sqlite3.Row) -> FileRecord:
    return FileRecord(
        id=row["id"],
        repository_id=row["repository_id"],
        path=row["path"],
        language=row["language"],
        hash=row["hash"],
        size_bytes=row["size_bytes"],
        mtime=row["mtime"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
