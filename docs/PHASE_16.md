# Phase 16 — Incremental Indexing

## What was built

Indexing never rebuilds everything. Each run diffs the working tree against the
persisted manifest by content hash and touches only what changed.

## Behaviour

- **Added / changed / removed** files are the only ones written; unchanged files
  are never re-read or re-parsed (`IndexReport.touched == 0` on a clean re-run).
- **Propagation via cascade:** when a file changes or is removed, its symbols are
  deleted (`delete_for_file` / FK cascade), which in turn cascades to that file's
  `enriched_symbols` and `embeddings`. So derived AI data for changed files is
  invalidated automatically and re-created on the next `enrich` / `embed`.
- **Embeddings** are additionally hash-gated: an unchanged embedding input is
  skipped; a changed one is re-embedded and overwrites in place in Qdrant.
- `update` reports how much was invalidated so the operator knows to re-run the
  optional AI layers.

## Resumability & cache

The SQLite manifest is a persistent cache: interrupting and re-running only
processes the remaining delta. No separate cache layer is needed.

## Known limitation

Dependent propagation is structural (cascade of a changed file's own derived
data). Invalidating *callers'* enrichment when a callee's meaning changes is a
heuristic future refinement; the call graph needed for it already exists
(`dependencies/callgraph.py`).

## Definition of Done

- [x] Only changed files are updated (AST, symbols, embeddings, metadata).
- [x] Changed/removed files propagate to their derived data via cascade.
- [x] Verified by the incremental indexer tests (add/change/remove, no-op re-run).
