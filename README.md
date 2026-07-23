# Code Intelligence Platform

A local-first system that ingests any software repository and produces a
queryable knowledge base combining **deterministic static analysis** with an
**optional AI enrichment** layer. It is designed to serve as a context-retrieval
backend for AI coding agents and for human questions about a codebase.

## Core principle

Deterministic analysis (facts) and AI reasoning (understanding) are always
separate layers. Parsing, symbols, and the structural graph must work fully
with AI enrichment disabled. The LLM never parses source structure and never
searches the repository directly — all access goes through the retrieval layer.

## Status

Built incrementally, phase by phase. Each phase ships working code, tests, a
`docs/PHASE_N.md` note, and a runnable capability. See `docs/` for per-phase
notes.

| Phase | Capability | State |
|-------|------------|-------|
| 1 | Repository ingestion (incremental manifest) | ✅ shipped |
| 2 | Tree-sitter parsing → symbols queryable by path | ✅ shipped |
| 3 | Structural knowledge graph (NetworkX, swappable) | ✅ shipped |
| 4 | Symbol index (exact/prefix/fuzzy search) | ✅ shipped |
| 5 | Dependency analysis & health report (`stats`) | ✅ shipped |
| 6 | AI enrichment (optional LLM layer) | ✅ shipped |
| 7 | Embedding pipeline (logical units) | ✅ shipped |
| 8 | Vector store (embedded Qdrant) | ✅ shipped |
| 9 | Keyword search (ripgrep + Python fallback) | ✅ shipped |
| 10 | Hybrid retrieval (all five sources) | ✅ shipped |
| 11 | Hierarchical summaries (`explain`) | ✅ shipped |
| 12 | Grounded Q&A with citations (`ask`) | ✅ shipped |
| 13 | Repository intelligence (`intel`, diffable) | ✅ shipped |
| 14 | Full CLI surface | ✅ shipped |
| 15 | FastAPI HTTP API (`serve`) | ✅ shipped |
| 16 | Incremental indexing + propagation | ✅ shipped |
| 17 | Configurable local LLM client | ✅ shipped |
| 18 | Parallel parsing, progress, resumable | ✅ shipped |
| 19 | Documentation (`docs/`) | ✅ shipped |
| 20 | Test suite (unit + integration + API) | ✅ shipped |
| 21 | Ontology & pattern detection | ✅ shipped |
| 22 | Change impact analysis (`impact`) | ✅ shipped |

## Requirements

- Python 3.12 (managed via [`uv`](https://docs.astral.sh/uv/))

## Setup

```bash
uv sync
```

## Usage (Phase 1)

Index a repository (creates `<repo>/.code-intel/index.db` by default):

```bash
uv run code-intel index /path/to/repo
```

Re-running only touches files whose contents changed:

```bash
uv run code-intel index /path/to/repo          # first run: everything added
uv run code-intel index /path/to/repo          # second run: all unchanged
```

Machine-readable output and store health:

```bash
uv run code-intel index /path/to/repo --json
uv run code-intel health /path/to/repo
```

Inspect extracted symbols (Phase 2):

```bash
uv run code-intel symbols /path/to/repo                      # type breakdown
uv run code-intel symbols /path/to/repo --file src/app.py    # symbols in a file
```

Explore, analyse, search, and retrieve (Phases 3–10):

```bash
uv run code-intel graph Indexer --path .                     # graph neighbourhood
uv run code-intel symbol authenticate --path . --type function
uv run code-intel stats /path/to/repo                        # dependency & health report
uv run code-intel search --keyword TODO --path . -C 2        # keyword/regex search
uv run code-intel retrieve "authentication flow" --path .    # hybrid retrieval

# Optional AI layers (need a local OpenAI-compatible endpoint for enrich):
uv run code-intel enrich /path/to/repo --limit 50
uv run code-intel embed  /path/to/repo                       # vectors → local Qdrant
```

Override the database location:

```bash
uv run code-intel index /path/to/repo --db /tmp/my-index.db
# or
CODE_INTEL_DB=/tmp/my-index.db uv run code-intel index /path/to/repo
```

## Browser UI / HTTP API

The whole pipeline is reachable over HTTP, and a browser UI is served from the
same process so you only need the terminal to launch it. `uvicorn` is an optional
dependency:

```bash
uv sync --extra serve         # or: uv add uvicorn
uv run code-intel ui          # serve API + UI and open the browser
uv run code-intel serve       # serve without opening a browser
```

- The UI is served at `http://127.0.0.1:8000/` when a built frontend is present
  (packaged under `code_intel/webui/`, overridable via `CODE_INTEL_UI_DIR`). Until
  the frontend is built, a placeholder page is shown and the API is fully usable.
- All endpoints are namespaced under `/api` (interactive schema at `/docs`).
  Indexing, updating, enriching, and embedding run as **background jobs**: the POST
  returns a job id, and you poll `GET /api/jobs/{id}` for progress and the result.
- Indexed repositories are remembered in `~/.code-intel/registry.json` (override
  `CODE_INTEL_REGISTRY`) so the UI can list them without re-typing paths.

The browser UI is a Next.js app in `web/`, built to a static export and served by
FastAPI (no Node process at runtime). To (re)build it into the package:

```bash
cd web && pnpm install && pnpm build:webui   # → src/code_intel/webui/
```

Surface: a repository dashboard (browse-to-add, index/update/delete with live
progress), a per-repository overview (stats, languages, findings with provenance),
search (keyword / symbol / hybrid), a symbols browser, a source viewer, an
interactive graph explorer, grounded Q&A (`ask`), explain, impact, an intelligence
findings view (filter by origin/category/confidence), and AI-layer runners
(enrich/embed with progress) plus the effective config. Every relationship and
finding shows its origin (static vs LLM) and confidence.

Frontend dev loop (hot reload; never needed just to run the tool): `uv run
code-intel serve` in one terminal, `cd web && pnpm dev` in another (it proxies to
`:8000`). Frontend smoke test: `PLAYWRIGHT_BASE_URL=http://127.0.0.1:8000 pnpm e2e`
against a running server.

## Development

```bash
uv run pytest          # tests
uv run ruff check src tests
uv run mypy
```

## Storage boundaries (do not violate)

- **SQLite** — metadata and deterministic relational facts.
- **NetworkX** — structural graph (later phase).
- **Qdrant** — embeddings / semantic store (later phase).

Each store owns exactly one kind of data. The graph is never stored in Qdrant;
embeddings are never stored in SQLite.
