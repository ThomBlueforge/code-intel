# Phase 20 — Testing

## What was built

A test suite spanning every layer, run with `uv run pytest`.

## Coverage by type

| Type | Tests |
|------|-------|
| Parser / extraction | `test_extractor` (10 languages, visibility, parents, robustness) |
| Ingestion / incremental | `test_indexer`, `test_scanner`, `test_hashing`, `test_languages` |
| Symbols | `test_symbol_index`, `test_symbol_indexing` |
| Graph | `test_graph` |
| Dependencies / impact | `test_dependencies`, `test_impact` |
| Enrichment | `test_enrichment` (fake client) |
| Embeddings | `test_embeddings` |
| Vector store | `test_vectorstore` (embedded Qdrant) |
| Keyword search | `test_keyword_search` |
| Retrieval | `test_retrieval` (with & without vectors) |
| Understanding / QA | `test_understanding`, `test_qa` |
| Intelligence / patterns | `test_intelligence` |
| Config | `test_config` |
| API (integration) | `test_api` (FastAPI TestClient, end-to-end) |

## Principles applied

- **Deterministic, offline** — the fake `ChatClient` and the hashing embedding
  provider mean the whole suite runs with no network or model server.
- **Behavioural** — tests assert observable behaviour (results, persistence,
  degradation), not internal structure.
- **AAA structure** and descriptive names throughout.

## How to run

```bash
uv run pytest                                  # full suite
uv run pytest --cov=src --cov-report=term-missing
uv run ruff check src tests                    # lint
uv run mypy                                     # strict type check
```

## Definition of Done

- [x] Unit, integration (API), parser, graph, embedding, retriever, and QA
      tests; all green.
- [x] The suite runs fully offline and gates every phase.
