# Architecture

## Layer separation (non-negotiable)

```
Repository
    │
    ▼
Deterministic layer  ──────────────  AI layer (optional)
  ingestion, parsing,                  enrichment, summaries,
  symbols, graph,                      Q&A — enriches, never
  dependencies                         overrides facts
    │                                      │
    └──────────────┬───────────────────────┘
                   ▼
            Hybrid retrieval  ──►  Local LLM (via retrieval only)
```

The deterministic layer (parsing → symbols → graph → dependencies) produces
**facts** and runs fully with the AI layer disabled. The AI layer produces
**understanding** that references facts by id and never rewrites them. The LLM
never parses source structure (Tree-sitter does) and never searches the repo
(retrieval does).

## Storage boundaries

| Store | Owns | Never holds |
|-------|------|-------------|
| **SQLite** | metadata + relational facts (files, symbols, enrichment, summaries, findings, embedding *records*) | vectors, the graph |
| **NetworkX** | structural graph (behind `GraphStore`, swappable for Neo4j) | embeddings |
| **Qdrant** | embedding vectors + payloads (embedded local mode) | the graph, SQLite facts |

## Data model (SQLite, schema v5)

- `repositories(id, path, name, …)`
- `files(id, repository_id, path, language, hash, …)`
- `symbols(id, repository_id, file_id, name, type, language, path, start_line, end_line, signature, visibility, parent_id, code, hash, …)`
- `enriched_symbols(symbol_id → symbols, summary, business_domain, architecture_layer, responsibilities, quality_metrics, risks, technical_debt, confidence, model, …)`
- `embeddings(symbol_id → symbols, model, dimension, content_hash, …)` — record only, no vector
- `summaries(scope, target_key, path, summary, source, confidence, …)`
- `findings(id, repository_id, category, title, detail, origin, confidence, target, …)`

All list/object columns are JSON text; timestamps are ISO-8601 UTC.

## Package layout

```
code_intel/
  ingestion/     scanner, hashing, languages, incremental indexer
  parsing/       tree-sitter queries + symbol extractor
  graph/         GraphStore interface + NetworkX impl + builder
  symbols/       ranked symbol search
  dependencies/  relationships, call graph, analysis, impact
  enrichment/    prompts + enricher (LLM)
  embeddings/    provider + pipeline + sink
  vectorstore/   Qdrant store
  keyword_search/ ripgrep + Python backends
  retrieval/     hybrid retriever
  understanding/ summaries + Q&A
  intelligence/  patterns + findings report
  llm/           OpenAI-compatible client
  storage/       SQLite database + repository-pattern DAOs
  cli/           Typer commands
  api/           FastAPI app
```

## Retrieval flow

```
Query → symbol search ┐
        keyword search ┤
        graph traversal ├─► merge + rank (semantic, exact, keyword,
        vector search  ┤     graph proximity, consensus, recency)
        metadata filter ┘        │
                                 ▼
                    ranked, deduplicated results
                                 │
                     (Q&A) bounded context → LLM → cited answer
```

## Provenance discipline

Every relationship/finding carries an `origin` (`STATIC_ANALYSIS` vs
`LLM_INFERENCE`) and a `confidence`. Deterministic and inferred results are
stored side by side but never merged by default — they are always filterable
apart.
