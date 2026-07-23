# Phase U1 — API gap-closing, background jobs, static UI hosting

First slice of the browser UI work. No frontend yet; this makes the whole
pipeline reachable over HTTP so the coming Next.js app can drive it, and lets a
single launch command serve both API and UI.

## What was built

- **Full API surface** (`api/routes.py`, namespaced under `/api`). Every CLI
  capability now has an endpoint:
  - Repositories/lifecycle: `GET /api/repos`, `GET /api/browse`, `GET /api/health`,
    `GET /api/config`, `POST /api/index`, `POST /api/update`, `DELETE /api/repo`.
  - Search & structure: `POST /api/search`, `GET /api/symbol`, `GET /api/symbols`
    (breakdown or per-file), `GET /api/graph`, `GET /api/file`, `POST /api/retrieve`.
  - Insights: `GET /api/stats`, `GET /api/explain`, `GET /api/impact`,
    `GET /api/intel` (`origin`, `diff`), `POST /api/ask`.
  - AI layers: `POST /api/enrich`, `POST /api/embed`.
  - Jobs: `GET /api/jobs`, `GET /api/jobs/{id}`.
- **Repository registry** (`registry.py`): a user-level `~/.code-intel/registry.json`
  (override `CODE_INTEL_REGISTRY`) recording which repositories have been indexed,
  so the UI can list them without re-typing paths. Written on every `index`/`update`
  (CLI and API) and cleared on `delete`. Convenience metadata only — never a source
  of truth for facts.
- **Background jobs** (`api/jobs.py`): `index`, `update`, `enrich`, and `embed` run
  in daemon threads. The POST returns a job snapshot (`id`, `status`, `progress`);
  the client polls `GET /api/jobs/{id}` for the final `result` or an `error`. Index
  progress is wired to the existing `Indexer.index(progress=)` callback.
- **Static UI hosting** (`api/app.py`): when a built UI is present it is mounted at
  `/` via `StaticFiles` (packaged `code_intel/webui/`, override `CODE_INTEL_UI_DIR`).
  A placeholder page ships until the Next.js export lands. The `/api` routes always
  take precedence over the static mount.
- **Launch**: `code-intel serve` (unchanged) plus a new `code-intel ui` command that
  serves and opens the browser. `uvicorn` is an optional `serve` extra
  (`uv sync --extra serve` or `uv add uvicorn`).

## Design notes

- The API stays a thin adapter layer: no analysis logic lives in `api/`. Endpoints
  call the same library the CLI calls.
- Deterministic endpoints work with AI disabled; `ask` only constructs an LLM client
  when `use_llm` is set, and `retrieve`/`ask` use vectors only if embeddings exist.
- Findings from `intel` carry `origin` (`STATIC_ANALYSIS` vs `LLM_INFERENCE`) and
  `confidence` in the JSON, ready for the UI's provenance badges.
- Jobs are in-process and non-persistent (single-user, localhost tool); a restart
  clears the job list. Concurrent writes to one repo DB are not serialised — fine for
  interactive single-user use.

## Definition of Done

- [x] Every CLI capability has an `/api` endpoint.
- [x] Repo registry records/lists/removes indexed repositories.
- [x] Long operations run as background jobs with pollable progress.
- [x] Static UI directory is served at `/` when present; API is reachable regardless.
- [x] Gate green: `ruff` clean, `mypy --strict` clean, full `pytest` suite passing
      (API + registry + jobs tests added).
