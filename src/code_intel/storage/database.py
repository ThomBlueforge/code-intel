"""SQLite connection management and schema.

Owns the on-disk database file and its schema migrations. A single writer
connection is used (Phase 1 is single-threaded); WAL mode is enabled so later
read concurrency is cheap. The schema is versioned via ``schema_meta`` so
future phases can migrate without rebuilding.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import TracebackType

SCHEMA_VERSION = 5

_SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS schema_meta (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS repositories (
        id         TEXT PRIMARY KEY,
        path       TEXT NOT NULL UNIQUE,
        name       TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS files (
        id            TEXT PRIMARY KEY,
        repository_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
        path          TEXT NOT NULL,
        language      TEXT NOT NULL,
        hash          TEXT NOT NULL,
        size_bytes    INTEGER NOT NULL,
        mtime         REAL NOT NULL,
        created_at    TEXT NOT NULL,
        updated_at    TEXT NOT NULL,
        UNIQUE (repository_id, path)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_files_repo ON files (repository_id)",
    "CREATE INDEX IF NOT EXISTS idx_files_language ON files (language)",
    """
    CREATE TABLE IF NOT EXISTS symbols (
        id            TEXT PRIMARY KEY,
        repository_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
        file_id       TEXT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
        name          TEXT NOT NULL,
        type          TEXT NOT NULL,
        language      TEXT NOT NULL,
        path          TEXT NOT NULL,
        start_line    INTEGER NOT NULL,
        end_line      INTEGER NOT NULL,
        signature     TEXT NOT NULL,
        visibility    TEXT NOT NULL,
        parent_id     TEXT REFERENCES symbols(id) ON DELETE SET NULL,
        code          TEXT NOT NULL,
        hash          TEXT NOT NULL,
        created_at    TEXT NOT NULL,
        updated_at    TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_symbols_repo ON symbols (repository_id)",
    "CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols (file_id)",
    "CREATE INDEX IF NOT EXISTS idx_symbols_path ON symbols (repository_id, path)",
    "CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols (name)",
    "CREATE INDEX IF NOT EXISTS idx_symbols_type ON symbols (type)",
    # AI enrichment, stored separately from deterministic facts and joinable by
    # symbol_id. List/dict fields are JSON-encoded text.
    """
    CREATE TABLE IF NOT EXISTS enriched_symbols (
        symbol_id          TEXT PRIMARY KEY REFERENCES symbols(id) ON DELETE CASCADE,
        summary            TEXT NOT NULL,
        business_domain    TEXT NOT NULL,
        architecture_layer TEXT NOT NULL,
        responsibilities   TEXT NOT NULL,
        quality_metrics    TEXT NOT NULL,
        risks              TEXT NOT NULL,
        technical_debt     TEXT NOT NULL,
        confidence         REAL NOT NULL,
        model              TEXT NOT NULL,
        created_at         TEXT NOT NULL,
        updated_at         TEXT NOT NULL
    )
    """,
    # Embedding traceability. The vector lives in the vector store (Qdrant), not
    # here — this row only records that an embedding exists for a symbol.
    """
    CREATE TABLE IF NOT EXISTS embeddings (
        symbol_id    TEXT PRIMARY KEY REFERENCES symbols(id) ON DELETE CASCADE,
        model        TEXT NOT NULL,
        dimension    INTEGER NOT NULL,
        content_hash TEXT NOT NULL,
        created_at   TEXT NOT NULL
    )
    """,
    # Hierarchical summaries (repository memory), separate from raw embeddings.
    """
    CREATE TABLE IF NOT EXISTS summaries (
        scope       TEXT NOT NULL,
        target_key  TEXT NOT NULL,
        path        TEXT NOT NULL,
        summary     TEXT NOT NULL,
        source      TEXT NOT NULL,
        confidence  REAL NOT NULL,
        created_at  TEXT NOT NULL,
        PRIMARY KEY (scope, target_key)
    )
    """,
    # Repository intelligence findings; origin + confidence keep deterministic
    # and inferred findings separable.
    """
    CREATE TABLE IF NOT EXISTS findings (
        id            TEXT PRIMARY KEY,
        repository_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
        category      TEXT NOT NULL,
        title         TEXT NOT NULL,
        detail        TEXT NOT NULL,
        origin        TEXT NOT NULL,
        confidence    REAL NOT NULL,
        target        TEXT NOT NULL,
        created_at    TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_findings_repo ON findings (repository_id)",
    "CREATE INDEX IF NOT EXISTS idx_summaries_path ON summaries (path)",
)


class Database:
    """Thin wrapper around a SQLite connection with schema bootstrap."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._conn: sqlite3.Connection | None = None

    @property
    def connection(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not open; call connect() first")
        return self._conn

    def connect(self) -> Database:
        """Open the connection, create the file/dir if needed, apply schema."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        self._conn = conn
        self._apply_schema()
        return self

    def _apply_schema(self) -> None:
        conn = self.connection
        with conn:
            for statement in _SCHEMA_STATEMENTS:
                conn.execute(statement)
            conn.execute(
                "INSERT INTO schema_meta (key, value) VALUES ('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(SCHEMA_VERSION),),
            )

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> Database:
        return self.connect()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
