# Phase 8 — Vector Database (Qdrant)

## What was built

A local, server-free Qdrant vector store (`QdrantClient(path=...)`) that
persists embedding vectors and payloads, and implements the `VectorSink`
protocol so the Phase 7 pipeline writes to it unchanged. `code-intel embed` now
persists into it.

### Module

- `vectorstore/qdrant_store.py` — `QdrantVectorStore`: upsert, delete,
  metadata-filtered search, count; embedded local persistence under
  `<repo>/.code-intel/qdrant/`.

## Capabilities

- **Incremental upsert** — a symbol's UUID is its point id, so re-embedding
  overwrites in place (no duplicates, no stale vectors).
- **Delete / re-index** — points removed by symbol id.
- **Metadata filtering** — `search(vector, payload_filter=…)` builds a Qdrant
  `Filter` (e.g. `{"language": "Go"}`), so a filtered query can exclude a nearer
  vector that doesn't match.
- **Persistence** — data survives client close/reopen on the same path.
- **Cosine similarity** over the configured dimension (256 for the offline
  hashing provider).

## Storage boundary (respected)

Qdrant owns exactly one kind of data: embeddings. The structural graph never
lives here; SQLite never holds vectors. Collections beyond `symbols` (modules,
documentation, architecture, repository summaries) are planned extension points;
the MVP uses the `symbols` collection.

## How to run

```bash
uv run code-intel enrich /path/to/repo
uv run code-intel embed  /path/to/repo     # vectors now persist in local Qdrant
```

## Definition of Done

- [x] A metadata-filtered vector query returns correct, current results after an
      incremental update (tested: overwrite-in-place + filter + reopen).
- [x] Incremental update, delete, re-index, metadata filtering, persistence.
- [x] Implements `VectorSink`; `embed` persists to it.
- [x] Typed, `ruff`-clean, `mypy --strict`-clean.
- [x] Unit tests: upsert/search, filtered search, incremental overwrite,
      delete, persistence across reopen.
- [x] This doc; CLI exposes the capability.
