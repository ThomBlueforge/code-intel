# Phase 18 — Performance & Scale

## What was built

- **Parallel parsing** — `Indexer.index(..., jobs=N)` parses added/changed files
  in a thread pool while all DB writes stay serial and transactional. Each
  worker uses a thread-local `SymbolExtractor` (no shared query cache/parser).
  `code-intel index --jobs 8`.
- **Streaming progress** — an optional `progress(done, path)` callback fires as
  files are parsed, for live progress UIs.
- **Resumable indexing** — indexing is incremental (Phase 16); interrupting and
  re-running processes only the remaining delta.
- **Persistent cache** — the SQLite manifest *is* the cache: content hashes let
  re-runs skip unchanged files without re-parsing.

## Architecture for scale

Indexing is three phases per run:

1. Scan + manifest diff + file-record writes (one transaction).
2. Parse the pending delta (parallel, no DB held).
3. Symbol writes (one transaction).

Parsing — the CPU-heavy step — is the part that parallelises; keeping writes
serial avoids SQLite contention. Memory stays flat because the scanner streams.

## Targets & limitations

Designed toward large repositories (100k+ files) via the streaming scan +
incremental delta + parallel parse. True multi-*process* sharding and a
distributed graph/vector backend (Neo4j, hosted Qdrant) are the next scale step;
the interfaces (`GraphStore`, `VectorSink`) already allow swapping them in.

## Definition of Done

- [x] Parallel indexing (`--jobs`), streaming progress, resumable indexing,
      persistent hash-based cache.
- [x] Verified: a 12-file repo indexes with `jobs=4` and emits per-file progress.
