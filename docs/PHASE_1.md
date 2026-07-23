# Phase 1 — Repository Ingestion

## What was built

A recursive, `.gitignore`-aware, **incremental** repository scanner that
produces a persisted file manifest with content hashes. This is the
deterministic foundation every later phase builds on. No parsing, AST, or LLM
work happens here.

### Modules

| Module | Responsibility |
|--------|----------------|
| `config.py` | Central, non-hardcoded settings (DB path, scan limits, LLM stub for later phases). |
| `models.py` | Canonical `Repository` and `FileRecord` dataclasses. |
| `storage/database.py` | SQLite connection, WAL, versioned schema (`schema_meta`, `repositories`, `files`). |
| `storage/repositories.py` | Repository-pattern data access (`RepositoryStore`, `FileStore`). |
| `ingestion/languages.py` | Filename → canonical language mapping (closed vocabulary). |
| `ingestion/hashing.py` | Single-read BLAKE2b hashing + NUL-byte binary detection. |
| `ingestion/scanner.py` | Streaming directory walk with layered filtering. |
| `ingestion/indexer.py` | Scan → diff against manifest → persist only differences. |
| `cli/main.py` | `code-intel index`, `health`, `version`. |

### Data model (SQLite)

- `repositories(id, path, name, created_at, updated_at)`
- `files(id, repository_id, path, language, hash, size_bytes, mtime, created_at, updated_at)`
  with `UNIQUE(repository_id, path)`.
- Timestamps are ISO-8601 UTC; `path` is repository-relative POSIX; `hash` is a
  128-bit BLAKE2b hex digest.

## How to run

```bash
cd code-intel
uv sync
uv run code-intel index /path/to/repo      # first run adds all eligible files
uv run code-intel index /path/to/repo      # re-run reports everything unchanged
uv run code-intel index /path/to/repo --json
uv run code-intel health /path/to/repo
uv run pytest
```

## Incremental behaviour

On each run the indexer loads the persisted manifest and compares content
hashes:

- new path → **added** (INSERT)
- known path, hash differs → **changed** (UPDATE)
- known path, hash equal → **unchanged** (no write)
- persisted path no longer on disk → **removed** (DELETE)

`IndexReport.touched` (added + changed + removed) is `0` on a clean re-run,
which is the Phase-1 Definition-of-Done contract.

## Filtering order (cheapest first)

1. Always-ignored directory names (`node_modules`, `.git`, `dist`, …).
2. Root `.gitignore` / `.git/info/exclude` rules.
3. Language detection — unknown extensions are skipped.
4. Size cap and binary (NUL-byte) detection.

## Known limitations

- Only the **repository-root** `.gitignore` and `.git/info/exclude` are honoured;
  nested per-directory `.gitignore` files are not yet parsed.
- Files above `CODE_INTEL_MAX_FILE_BYTES` (default 5 MB) are counted as skipped,
  not indexed.
- Single-threaded. Parallel/resumable indexing is Phase 18.
- Symlinks are followed by `os.walk` defaults; cycle protection is not yet added.

## Definition of Done

- [x] Typed, linted (ruff), type-checked (mypy strict).
- [x] Unit tests for languages, hashing, scanner, and incremental indexer.
- [x] This doc.
- [x] CLI exposes the capability end-to-end (`index` / `health`).
- [x] Runs start-to-finish against a real sample repository.
