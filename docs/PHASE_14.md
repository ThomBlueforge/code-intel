# Phase 14 — CLI

## What was built

The full command surface, each a thin adapter over the library.

| Command | Purpose |
|---------|---------|
| `index` | Index a repository (incremental); `--jobs` parallel parsing. |
| `update` | Incremental re-index (alias for `index`, reports invalidation). |
| `delete` | Remove a repository's knowledge base. |
| `search --keyword` | Keyword/regex search with context. |
| `graph` | Structural graph neighbourhood of a symbol. |
| `symbol` | Ranked symbol search. |
| `symbols` | Symbols in a file / type breakdown. |
| `stats` | Dependency & health report. |
| `retrieve` | Hybrid retrieval across all sources. |
| `explain` | Hierarchical summary at any granularity. |
| `ask` | Grounded Q&A with citations. |
| `impact` | Change-impact analysis. |
| `intel` | Repository intelligence findings (with `--diff`). |
| `enrich` | AI enrichment (optional LLM). |
| `embed` | Embed enriched symbols into Qdrant. |
| `config` | Show effective configuration. |
| `serve` | Run the HTTP API. |
| `health` / `version` | Store check / version. |

## Definition of Done

- [x] All roadmap commands (`index`, `update`, `delete`, `search`, `graph`,
      `symbol`, `ask`, `stats`, `health`, `explain`) plus extras are implemented.
- [x] Each command is a thin adapter; no business logic in the CLI.
