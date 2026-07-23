# Phase 4 — Symbol Index

## What was built

Ranked symbol search over the deterministic symbol table. `code-intel symbol
<query>` returns matches ordered by relevance, with language / type / path
filters.

### Module

- `symbols/index.py` — `SymbolIndex.search(...)` returning `SymbolHit` records
  (id, name, type, language, path, visibility, lines, score, match type).

## Matching model

Each candidate name is scored against the query:

| Match | Condition | Score |
|-------|-----------|-------|
| exact | name == query (case-insensitive) | 1.0 |
| prefix | name starts with query | ~0.9, length-penalised |
| substring | query inside name | ≥ 0.7 |
| fuzzy | `difflib` ratio | ratio (dropped below 0.45) |

Results sort by score, then shorter name, then path/line. Filters
(`languages`, `types`, `path_prefix`) are pushed into SQL; the heavy `code`
column is never selected, keeping search lightweight.

## How to run

```bash
uv run code-intel symbol login --path .
uv run code-intel symbol auth --path . --type class
uv run code-intel symbol Authenticate --path . --lang Go
uv run code-intel symbol handler --path . --in src/ --limit 10
```

## Performance

SQLite indexes on `name` and `(repository_id, path)` plus Python-side scoring of
a filtered candidate set keep this well under the 200 ms target on mid-size
repositories (asserted in `test_search_is_fast`). On very large repos, narrow
with `--lang` / `--type` / `--in`, which reduce the candidate set in SQL.

## Definition of Done

- [x] Exact, prefix, and fuzzy search with language/type/path filters.
- [x] `code-intel symbol <query>` returns ranked matches in < 200 ms.
- [x] Typed, `ruff`-clean, `mypy --strict`-clean.
- [x] Unit tests: exact/prefix/fuzzy, each filter, empty query, latency.
- [x] This doc; CLI exposes the capability.
