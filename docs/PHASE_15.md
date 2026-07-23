# Phase 15 — FastAPI

## What was built

An HTTP surface (`code_intel/api/app.py`) over the same library the CLI uses.
Run it with `code-intel serve` or `uvicorn code_intel.api.app:app`.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/index` | Index a repository (`{"path": …}`). |
| POST | `/update` | Incremental re-index. |
| POST | `/search` | Keyword search. |
| POST | `/ask` | Grounded Q&A with citations. |
| GET | `/symbol` | Ranked symbol search. |
| GET | `/graph` | Structural neighbourhood of a symbol. |
| GET | `/stats` | Dependency & health report. |
| GET | `/health` | Store status. |

Every endpoint names a repository `path` and returns JSON. Endpoints are thin
adapters — all logic lives in the library, so CLI and API never diverge.

## How to run

```bash
uv run code-intel serve --port 8000
# or
uv run uvicorn code_intel.api.app:app --reload
curl -X POST localhost:8000/index -d '{"path":"/repo"}' -H 'content-type: application/json'
curl 'localhost:8000/symbol?path=/repo&query=authenticate'
```

## Definition of Done

- [x] All roadmap endpoints implemented and returning JSON.
- [x] Reuses the library (no duplicated logic).
- [x] Typed, `ruff`-clean, `mypy --strict`-clean.
- [x] Tested with FastAPI's `TestClient` (index, symbol, graph, search, stats,
      ask, 404s).
