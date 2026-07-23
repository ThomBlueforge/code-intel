# Phase 10 — Hybrid Retrieval

## What was built

A single `retrieve(query)` that draws from **all five sources**, merges them per
symbol, deduplicates, and ranks. Exposed as `code-intel retrieve <query>` and
used as the retrieval backbone for Phase 12 Q&A.

### Module

- `retrieval/hybrid.py` — `HybridRetriever` + `RetrievalResult`.

## The five sources

1. **Symbol search** — ranked exact/prefix/fuzzy name match (Phase 4).
2. **Keyword search** — code text hits mapped to their enclosing symbol (Phase 9).
3. **Graph traversal** — neighbours of the top seeds via the structural graph
   (Phase 3).
4. **Vector search** — query embedded and matched against Qdrant (Phases 7–8);
   **optional** — skipped when no embeddings exist.
5. **Metadata filtering** — language / type filters applied across all sources.

## Ranking

Per-symbol signals are blended:

```
score = (0.30·symbol + 0.35·vector + 0.20·keyword + 0.15·graph + 0.05·recency)
        × (1 + 0.08·(sources − 1))
```

- Semantic and exact-symbol matches dominate; keyword and graph proximity
  refine; **cross-source consensus** (a symbol found by several sources) and
  recency are tie-breakers.
- Results are deduplicated by `symbol_id`; each result reports which sources
  contributed.

## Graceful degradation

The vector source is only added when both a vector store and an embedding
provider are supplied. With enrichment/embeddings disabled, `retrieve` still
returns ranked results from symbol + keyword + graph — the deterministic core
never depends on the AI layers.

## How to run

```bash
uv run code-intel retrieve "authentication flow" --path .
uv run code-intel retrieve "charge" --type function --lang Python --limit 5
```

(If `enrich` + `embed` have been run, the vector source joins automatically.)

## Definition of Done

- [x] A single `retrieve(query)` returns a ranked, deduplicated set drawing from
      all five sources.
- [x] Works with or without the vector source (deterministic degradation).
- [x] Typed, `ruff`-clean, `mypy --strict`-clean.
- [x] Unit tests: deterministic-only retrieval, merge/dedupe with provenance,
      graph-pulled relatives, type/language filters, vector-augmented retrieval,
      empty query.
- [x] This doc; CLI exposes the capability.
