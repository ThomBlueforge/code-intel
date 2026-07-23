# Phase 9 — Keyword Search (ripgrep)

## What was built

`code-intel search --keyword <term>` returns matching file/line/context across
indexed files, with exact or regex matching, case sensitivity, and language
filters.

### Module

- `keyword_search/searcher.py` — `KeywordSearcher` + `KeywordMatch`.

## Backends

`KeywordSearcher` uses **ripgrep** when the `rg` binary is resolvable (fast,
respects its own ignore rules) and a **pure-Python** scan otherwise. Both return
identical `KeywordMatch` shapes, and context lines are always assembled from the
file so the two agree. `backend_name` reports which ran.

> In this environment no standalone `rg` binary is on `PATH`, so the Python
> backend is active. Installing ripgrep (or setting a path) switches to it with
> no API change.

## Features

- Exact (fixed-string) or `--regex` matching.
- Case-insensitive by default; `--case`/`-i` toggles.
- `--lang` restricts to one or more languages (repeatable).
- `--context`/`-C` surrounding lines; `--limit` caps results.
- Scoped to the indexed file manifest (never wanders outside the repo).

## How to run

```bash
uv run code-intel search --keyword authenticate --path .
uv run code-intel search --keyword "def \w+\(" --regex --lang Python -C 1
uv run code-intel search --keyword TODO --limit 20
```

## Definition of Done

- [x] `code-intel search --keyword <term>` returns file / line / context.
- [x] Exact match, regex, case sensitivity, language filters, context.
- [x] Typed, `ruff`-clean, `mypy --strict`-clean.
- [x] Unit tests: exact+context, case sensitivity, regex, language filter,
      limit, empty query, backend selection.
- [x] This doc; CLI exposes the capability.
