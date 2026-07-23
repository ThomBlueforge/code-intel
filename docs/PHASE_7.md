# Phase 7 — Embedding Pipeline

## What was built

Embeds **complete logical units** (never arbitrary chunks). Runs after
enrichment, so each embedded unit carries deterministic facts *and* AI
understanding. Every enriched symbol gets a traceability record in SQLite
(`embeddings`), and the vector + rich payload is handed to a `VectorSink`.

### Modules

| Module | Responsibility |
|--------|----------------|
| `embeddings/provider.py` | `EmbeddingProvider` protocol; offline `HashingEmbeddingProvider` + `OpenAICompatibleEmbeddingProvider`. |
| `embeddings/sink.py` | `EmbeddedUnit`, `VectorSink` protocol, `InMemoryVectorSink` (with naive cosine search). |
| `embeddings/pipeline.py` | `EmbeddingPipeline`: build unit text → embed → record → sink. |
| `storage/repositories.py` | `EmbeddingStore` (metadata only, no vectors). |

## Storage boundary (respected)

The **vector never touches SQLite**. SQLite stores only
`embeddings(symbol_id, model, dimension, content_hash, created_at)` for
traceability and staleness detection. The vector goes to the sink — an in-memory
sink now, Qdrant in Phase 8.

## Embedded unit

Each `EmbeddedUnit` payload includes: symbol id, repository, path, name, kind,
language, parent symbol, summary, business domain, architecture layer, keywords
(derived from the identifier), complexity, content hash, line span, and the unit
source. The embedding input concatenates kind/name/language + summary + domain +
layer + full code.

## Providers

- **Hashing (default, offline):** deterministic feature-hashing into a 256-dim
  L2-normalised vector. No network, no model server — the pipeline and Phase 8
  vector search are fully testable offline.
- **OpenAI-compatible:** posts to a configured `/embeddings` endpoint, batched by
  `LLMSettings.batch_size`; dimension discovered from the response.

## How to run

```bash
uv run code-intel enrich /path/to/repo      # Phase 6 first
uv run code-intel embed  /path/to/repo      # then embed enriched symbols
```

## Incremental

A symbol whose embedding-input hash is unchanged is skipped unless `--force`,
so re-embedding only touches changed/enriched-anew symbols.

## Definition of Done

- [x] Only complete logical units are embedded (per-symbol), never raw chunks.
- [x] Every enriched symbol has an embedding record traceable by `symbol_id`.
- [x] Vector stays out of SQLite; payload carries the required metadata.
- [x] Typed, `ruff`-clean, `mypy --strict`-clean.
- [x] Unit tests: determinism/normalisation, record-per-enriched-symbol,
      traceability, payload metadata, incremental skip/force.
- [x] This doc; CLI exposes the capability.
