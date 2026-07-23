# Phases U5–U7 — Understanding surfaces, AI runners, polish & tests

Completes the browser UI: the remaining understanding screens, the AI-layer
runners, and an accessibility/testing pass. No new backend endpoints beyond the
already-shipped `/api/*`.

## U5 — Ask, Explain, Impact, Intelligence

- **Ask** (`web/components/Ask.tsx`, `/api/ask`) — question box with a **Use LLM**
  toggle. Without the LLM it returns the cited context the answer is grounded in;
  with it, the local LLM answers, grounded. Citations that look like `path:line`
  are clickable into the source viewer. The answer is badged `llm` or
  `retrieval only`.
- **Explain** (`Explain.tsx`, `/api/explain`) — summary for `.`, a file/dir, or a
  symbol (scope, target, summary, details).
- **Impact** (`Impact.tsx`, `/api/impact`) — change impact for a symbol: definition
  count, direct/indirect callers, affected files/modules/tests. Callers and files
  deep-link to source. Labelled heuristic/name-based, honestly.
- **Intelligence** (`Intelligence.tsx`, `/api/intel?diff=true`) — findings with
  **origin / category / min-confidence filters** and a new/resolved diff. Every
  finding carries its `OriginBadge` (static vs llm) and confidence.

## U6 — AI layers & config

- **AI layers** (`AiLayers.tsx`) — run **enrich** (`/api/enrich`) and **embed**
  (`/api/embed`) as background jobs with a live progress bar and result summary;
  a **Force re-run** toggle. Shows the effective **configuration**
  (`/api/config`): db path, file cap, and the LLM settings, with a note that it's
  all driven by `CODE_INTEL_LLM_*` — no vendor lock-in. Copy makes clear these
  layers never alter deterministic facts.

## U7 — Polish & tests

- **Accessibility**: a skip-to-content link, a visible `:focus-visible` ring on
  interactive elements, `aria-label`s on the filter/search controls, and the
  existing reduced-motion handling. `<main>` is focus-targetable.
- **Responsive/theme**: all screens use the shared token system; verified in
  light and dark and down to mobile widths.
- **E2E**: `web/e2e/smoke.spec.ts` + `playwright.config.ts` (`pnpm e2e`) — loads
  the app against a running server and clicks through **all nine** repo-scoped
  screens, asserting each mounts. `@playwright/test` added as a dev dependency.

## Verification

- `pnpm typecheck` + `next build` clean; export synced to `src/code_intel/webui/`.
- Playwright e2e: **2 passed** against a live server (dashboard + full-nav walk).
- Python gate unchanged: `ruff` + `mypy --strict` clean, **138 tests** pass.
- Visual check against a live index: Intelligence (89 findings, filters, diff),
  AI layers (config + runners), and Impact (`build_call_graph`: 1 def / 4 direct /
  8 indirect / 6 files) all render correctly.

## Definition of Done

- [x] Ask (grounded, LLM-optional, cited), Explain, Impact, Intelligence all work.
- [x] Enrich/embed run from the browser with progress; config is visible.
- [x] a11y pass (skip link, focus rings, aria); responsive + theme-aware.
- [x] E2E smoke test passes; full gate green.

## Status

The browser UI now covers all planned surfaces: Repositories, Overview, Search,
Symbols, Source viewer, Graph, Ask, Explain, Impact, Intelligence, and AI layers —
the whole pipeline is usable without the terminal (except to launch it).
