# Phase U2 — Browser app shell, repo dashboard, overview

First visible slice of the browser UI: a Next.js app served by FastAPI, with the
repository dashboard and per-repository overview working end to end against the
U1 API.

## What was built

- **Next.js app** (`web/`, App Router, TypeScript) built as a **static export**
  (`output: "export"`) and synced into `src/code_intel/webui/` (served by FastAPI
  at `/`). No Node process at runtime.
  - `web/lib/api.ts` — typed client for `/api/*`, including `pollJob` for the
    background-job flow. Same-origin in production; auto-targets `:8000` under
    `next dev`; override with `NEXT_PUBLIC_API_BASE`.
  - `web/app/page.tsx` — the shell: left-rail nav, repository switcher, theme
    toggle (system/light/dark, no-flash), and view routing.
  - `web/components/RepoDashboard.tsx` — list indexed repos, **browse the
    filesystem to add one**, and index / update / delete with a live job-progress
    bar driven by `pollJob`.
  - `web/components/Overview.tsx` — per-repo stats (files, symbols, call/import
    edges, cycles) + language bars + repository-intelligence findings.
  - `web/components/ui.tsx` — primitives (Panel, Button, Stat, Badge,
    `OriginBadge`, `JobProgressBar`, EmptyState, Spinner).
  - `web/app/globals.css` — an "engineering console" design system: graphite
    dark-first with a disciplined light mode, monospace for data/paths, one
    electric accent, responsive to 320px, reduced-motion aware.

## Design discipline reflected in the UI

- **Provenance is visible.** Every finding shows an `OriginBadge` — teal
  `static` (`STATIC_ANALYSIS`) vs violet `llm` (`LLM_INFERENCE`) — with its
  confidence; call/import-edge stats are labelled "static analysis".
- **Deterministic-first.** The overview renders entirely from deterministic
  endpoints; nothing here needs the AI layer.
- **Honest emptiness.** Zero states ("No findings", "No repositories indexed
  yet") are rendered explicitly rather than faked.

## Building the UI

```bash
cd web
pnpm install
pnpm build:webui   # next build (static export) + sync into src/code_intel/webui
```

Dev loop (two servers, hot reload — never required to *run* the tool):

```bash
# terminal 1: API
uv run code-intel serve
# terminal 2: UI dev server (proxies to :8000 automatically)
cd web && pnpm dev
```

## Verification

- `pnpm typecheck` and `next build` clean; static export serves via FastAPI
  (`/`, `/_next/*` assets return 200 with correct MIME types).
- Python gate unaffected: `ruff` + `mypy --strict` clean, 137 tests pass.
- Manual visual check against a real index (69 files / 1818 symbols): dashboard,
  overview, light + dark, and a 390px mobile layout all render correctly.

## Definition of Done

- [x] One launch command serves API + UI; opening the port shows the app.
- [x] Repositories can be discovered, added (via browse), indexed/updated/deleted
      from the browser with live progress — no terminal needed.
- [x] Overview shows real deterministic stats and intelligence with provenance.
- [x] Responsive, theme-aware, reduced-motion aware.

## Next (U3)

Search (keyword / symbol / hybrid retrieve) + symbols browser + source viewer.
