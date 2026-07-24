"""Ingestion orchestration.

Ties the scanner, the Tree-sitter symbol extractor, and the storage layer into
an incremental index operation: scan the working tree, diff it against the
persisted manifest, and apply only the differences inside a single transaction.
Unchanged files are never re-read or re-parsed, satisfying the "re-running only
touches changed files" contract.

Symbol extraction is deterministic and best-effort: a file whose language has
no parser, or that fails to parse, is still recorded in the manifest with zero
symbols. The manifest layer never depends on parsing succeeding.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from code_intel.config import Settings
from code_intel.ingestion.scanner import ScanCounters, ScannedFile, Scanner
from code_intel.models import FileRecord, Symbol, utc_now_iso
from code_intel.parsing.extractor import ParsedSymbol, SymbolExtractor
from code_intel.storage.database import Database
from code_intel.storage.repositories import FileStore, RepositoryStore, SymbolStore

# Progress callback: (files_parsed_so_far, relative_path).
ProgressFn = Callable[[int, str], None]

# Per-thread extractor so parallel parsing never shares a query cache/parser.
_thread_local = threading.local()


def _local_extractor() -> SymbolExtractor:
    extractor = getattr(_thread_local, "extractor", None)
    if extractor is None:
        extractor = SymbolExtractor()
        _thread_local.extractor = extractor
    return extractor


def _parse_task(item: tuple[str, ScannedFile]) -> tuple[str, ScannedFile, list[ParsedSymbol]]:
    file_id, scanned = item
    extractor = _local_extractor()
    if not extractor.supports(scanned.language):
        return file_id, scanned, []
    try:
        source = scanned.abs_path.read_bytes()
    except OSError:
        return file_id, scanned, []
    return file_id, scanned, extractor.extract(scanned.language, source)


@dataclass(frozen=True)
class IndexReport:
    """Summary of a single index run."""

    repository_id: str
    repository_path: str
    added: int
    changed: int
    unchanged: int
    removed: int
    symbols_parsed: int
    symbols_total: int
    counters: ScanCounters
    duration_s: float

    @property
    def total_indexed(self) -> int:
        return self.added + self.changed + self.unchanged

    @property
    def touched(self) -> int:
        """Files that required a write (the incremental work actually done)."""
        return self.added + self.changed + self.removed


class Indexer:
    """Runs ingestion (Phase 1) and symbol extraction (Phase 2) for a repo."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def index(
        self,
        repo_path: Path,
        *,
        jobs: int = 1,
        progress: ProgressFn | None = None,
    ) -> IndexReport:
        """Index ``repo_path``. ``jobs`` parallelises parsing; ``progress`` streams.

        Parsing (the expensive step) runs in a thread pool when ``jobs > 1``;
        all database writes stay serial and transactional. Only added/changed
        files are parsed, so this is resumable across runs (a persistent cache).
        """
        repo_path = repo_path.resolve()
        if not repo_path.is_dir():
            raise NotADirectoryError(f"Not a directory: {repo_path}")

        started = time.perf_counter()
        scanner = Scanner(self._settings.scan)

        with Database(self._settings.db_path) as db:
            conn = db.connection
            file_store = FileStore(conn)
            symbol_store = SymbolStore(conn)

            repository = RepositoryStore(conn).get_or_create(str(repo_path), repo_path.name)
            existing = file_store.manifest(repository.id)
            seen_paths: set[str] = set()
            pending: list[tuple[str, ScannedFile]] = []
            added = changed = unchanged = 0
            now = utc_now_iso()

            with conn:  # phase 1: file-manifest mutations
                for scanned in scanner.scan(repo_path):
                    seen_paths.add(scanned.rel_path)
                    prior = existing.get(scanned.rel_path)
                    if prior is None:
                        file_id = str(uuid.uuid4())
                        file_store.insert(_new_file(file_id, repository.id, scanned, now))
                        pending.append((file_id, scanned))
                        added += 1
                    elif prior.hash != scanned.hash:
                        file_store.update_content(
                            prior.id,
                            file_hash=scanned.hash,
                            size_bytes=scanned.size_bytes,
                            mtime=scanned.mtime,
                            updated_at=now,
                        )
                        symbol_store.delete_for_file(prior.id)
                        pending.append((prior.id, scanned))
                        changed += 1
                    else:
                        unchanged += 1

                removed_ids = [
                    entry.id for path, entry in existing.items() if path not in seen_paths
                ]
                file_store.delete_many(removed_ids)  # symbols cascade via FK

            # phase 2: parse pending files (parallel or serial), no DB involved
            parsed_results = self._parse(pending, jobs, progress)

            # phase 3: write symbols
            symbols_parsed = 0
            with conn:
                for file_id, scanned, parsed in parsed_results:
                    if not parsed:
                        continue
                    symbol_store.insert_many(
                        _to_symbols(file_id, scanned, parsed, repository.id, now)
                    )
                    symbols_parsed += len(parsed)
                if added or changed or removed_ids:
                    conn.execute(
                        "UPDATE repositories SET updated_at = ? WHERE id = ?",
                        (now, repository.id),
                    )

            symbols_total = symbol_store.count(repository.id)
            duration = time.perf_counter() - started
            return IndexReport(
                repository_id=repository.id,
                repository_path=str(repo_path),
                added=added,
                changed=changed,
                unchanged=unchanged,
                removed=len(removed_ids),
                symbols_parsed=symbols_parsed,
                symbols_total=symbols_total,
                counters=scanner.counters,
                duration_s=duration,
            )

    def _parse(
        self,
        pending: list[tuple[str, ScannedFile]],
        jobs: int,
        progress: ProgressFn | None,
    ) -> list[tuple[str, ScannedFile, list[ParsedSymbol]]]:
        if not pending:
            return []
        results: list[tuple[str, ScannedFile, list[ParsedSymbol]]] = []
        if jobs > 1 and len(pending) > 1:
            with ThreadPoolExecutor(max_workers=jobs) as pool:
                iterator = pool.map(_parse_task, pending)
                for done, result in enumerate(iterator, start=1):
                    results.append(result)
                    if progress is not None:
                        progress(done, result[1].rel_path)
        else:
            for done, item in enumerate(pending, start=1):
                result = _parse_task(item)
                results.append(result)
                if progress is not None:
                    progress(done, result[1].rel_path)
        return results


def _new_file(file_id: str, repository_id: str, scanned: ScannedFile, now: str) -> FileRecord:
    return FileRecord(
        id=file_id,
        repository_id=repository_id,
        path=scanned.rel_path,
        language=scanned.language,
        hash=scanned.hash,
        size_bytes=scanned.size_bytes,
        mtime=scanned.mtime,
        created_at=now,
        updated_at=now,
    )


def _to_symbols(
    file_id: str,
    scanned: ScannedFile,
    parsed: list[ParsedSymbol],
    repository_id: str,
    now: str,
) -> list[Symbol]:
    return [
        Symbol(
            id=ps.id,
            repository_id=repository_id,
            file_id=file_id,
            name=ps.name,
            type=ps.type,
            language=scanned.language,
            path=scanned.rel_path,
            start_line=ps.start_line,
            end_line=ps.end_line,
            signature=ps.signature,
            visibility=ps.visibility,
            parent_id=ps.parent_id,
            code=ps.code,
            hash=ps.hash,
            created_at=now,
            updated_at=now,
            decorators=ps.decorators,
        )
        for ps in parsed
    ]
