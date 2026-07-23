# Phase 11 — Repository Understanding

## What was built

Hierarchical summaries — symbol → module → package → repository — stored as
repository memory (`summaries` table), plus `code-intel explain <target>` that
returns a summary at the right granularity.

### Module

- `understanding/summaries.py` — `SummaryBuilder` (`build_repository`, `explain`).

## How summaries are made

Bottom-up and deterministic, reusing AI enrichment when present:

- **Symbol** — the enriched summary if available, else a deterministic
  description from type/name/signature.
- **Module (file)** — symbol counts by kind, key names, and how many carry AI
  summaries.
- **Package (directory)** — module rollup.
- **Repository** — files, symbols, languages, and enrichment coverage.

Works fully with the LLM disabled; enrichment only improves the leaf summaries.

## How to run

```bash
uv run code-intel explain .                 # whole repository
uv run code-intel explain src/app.py        # a module
uv run code-intel explain src               # a package
uv run code-intel explain authenticate      # a symbol
```

## Definition of Done

- [x] `code-intel explain <path>` returns a granularity-appropriate summary.
- [x] Summaries stored separately from raw embeddings (repository memory).
- [x] Typed, `ruff`-clean, `mypy --strict`-clean; unit-tested.
- [x] CLI exposes the capability.
