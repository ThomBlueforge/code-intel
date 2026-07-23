"""Shared HTTP plumbing for the API routes.

Holds the request/response schemas, the per-request repository context (open the
right SQLite store, resolve the repository row), and the directory-browse helper
that powers the UI's repo picker. Route handlers stay thin adapters over the same
library the CLI calls; nothing here contains analysis logic.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel

from code_intel.config import DATA_DIR_NAME, DEFAULT_DB_FILENAME, Settings
from code_intel.registry import RepositoryRegistry
from code_intel.storage.database import Database
from code_intel.storage.repositories import RepositoryStore


class PathBody(BaseModel):
    path: str


class SearchBody(BaseModel):
    path: str
    keyword: str
    regex: bool = False
    case_sensitive: bool = False
    languages: list[str] | None = None
    limit: int = 50


class AskBody(BaseModel):
    path: str
    question: str
    use_llm: bool = False


class RetrieveBody(BaseModel):
    path: str
    query: str
    limit: int = 10
    languages: list[str] | None = None
    types: list[str] | None = None


class EnrichBody(BaseModel):
    path: str
    limit: int | None = None
    force: bool = False
    base_url: str | None = None
    model: str | None = None


class EmbedBody(BaseModel):
    path: str
    limit: int | None = None
    force: bool = False


def settings_for(path: str) -> Settings:
    """Resolve settings for a repository path (honours CODE_INTEL_* env)."""
    return Settings.for_repository(Path(path).resolve())


class RepoContext:
    """Opens a repository's store and resolves its repository row.

    Raises 404 if the repository has not been indexed at this path.
    """

    def __init__(self, path: str) -> None:
        self._path = path
        self._db: Database | None = None

    def __enter__(self) -> tuple[Any, Any]:
        settings = settings_for(self._path)
        if not settings.db_path.exists():
            raise HTTPException(status_code=404, detail="Repository not indexed")
        self._db = Database(settings.db_path).connect()
        repo = RepositoryStore(self._db.connection).get_by_path(
            str(Path(self._path).resolve())
        )
        if repo is None:
            self._db.close()
            raise HTTPException(status_code=404, detail="Repository not indexed at this path")
        return self._db.connection, repo

    def __exit__(self, *exc: object) -> None:
        if self._db is not None:
            self._db.close()


def open_repo(path: str) -> RepoContext:
    return RepoContext(path)


def browse_directory(dir_arg: str | None) -> dict[str, Any]:
    """List sub-directories of ``dir_arg`` (or the user's home) for the picker.

    Directories only; hidden directories are omitted to keep the picker clean.
    Each entry is flagged ``indexed`` when it already has a ``.code-intel`` store.
    """
    base = Path(dir_arg).expanduser() if dir_arg else Path.home()
    try:
        base = base.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=f"Not a directory: {dir_arg}") from exc
    if not base.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {base}")

    entries: list[dict[str, Any]] = []
    try:
        children = sorted(base.iterdir(), key=lambda p: p.name.lower())
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"Cannot read: {base}") from exc
    registered = {e.path for e in RepositoryRegistry().list()}
    for child in children:
        if child.name.startswith(".") or not child.is_dir():
            continue
        local_store = (child / DATA_DIR_NAME / DEFAULT_DB_FILENAME).exists()
        indexed = local_store or str(child.resolve()) in registered
        entries.append({"name": child.name, "path": str(child), "indexed": indexed})

    parent = str(base.parent) if base.parent != base else None
    return {"path": str(base), "parent": parent, "entries": entries}


def read_file_snippet(
    repo_path: str, rel_file: str, start: int, end: int | None
) -> dict[str, Any]:
    """Read a line range of a repository file, guarding against path escape."""
    root = Path(repo_path).resolve()
    target = (root / rel_file).resolve()
    try:
        within = os.path.commonpath([str(root), str(target)]) == str(root)
    except ValueError:
        within = False
    if not within:
        raise HTTPException(status_code=400, detail="Path escapes repository")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise HTTPException(status_code=404, detail="File not readable") from exc

    lines = text.splitlines()
    total = len(lines)
    first = max(1, start)
    last = total if end is None else min(end, total)
    snippet = lines[first - 1 : last] if first <= total else []
    return {
        "file": rel_file,
        "start": first,
        "end": last,
        "total_lines": total,
        "lines": snippet,
    }
