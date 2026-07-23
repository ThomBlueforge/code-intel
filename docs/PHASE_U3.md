# Phase U3 — Search, symbols browser, source viewer

Adds the three exploration surfaces to the browser UI, all wired to a shared
source viewer.

## What was built

- **`GET /api/files`** (new endpoint) — lists a repository's files (`path`,
  `language`) so the UI can build a file browser. Thin adapter over
  `FileStore.list_records`; test in `tests/test_api.py`.
- **Search** (`web/components/Search.tsx`) — one search box with three modes:
  - **Hybrid** (`/api/retrieve`) — semantic + structural ranking; results show
    the score and which sources matched (symbol/keyword/graph/vector chips).
  - **Symbol** (`/api/symbol`) — ranked name search with match-type badges
    (exact / prefix / substring / fuzzy).
  - **Keyword** (`/api/search`) — text/regex with the ripgrep-or-Python backend
    surfaced.
  Every result deep-links into the source viewer at its location.
- **Symbols browser** (`web/components/Symbols.tsx`) — a filterable file list on
  the left; selecting a file lists its symbols (kind, name, parent, visibility,
  line range). Clicking a symbol opens it in the source viewer.
- **Source viewer** (`web/components/SourceViewer.tsx`) — a modal that fetches a
  file via `/api/file`, renders it with line numbers, highlights the focused
  line range, auto-scrolls to it, and closes on Escape/backdrop. Shared by
  Search and Symbols and lifted to `app/page.tsx` so any screen can open it.
- Search and Symbols nav items are now enabled; `app/page.tsx` owns the
  `SourceViewer` overlay and the `onOpenSource(file, start?, end?)` callback.

## Notes

- All three surfaces are deterministic — no AI layer required. The path-escape
  guard in `/api/file` is exercised by the source viewer.
- The `/api/file` read returns the whole file; the viewer highlights and scrolls
  to the target. Large files scroll within the modal (its own overflow), so the
  page body never scrolls horizontally.

## Verification

- `pnpm typecheck` + `next build` clean; export synced to `src/code_intel/webui/`.
- Python gate: `ruff` + `mypy --strict` clean, **138 tests** pass (adds
  `test_files`).
- Visual check against a live index: symbols browser (file → symbols), source
  viewer (focused line highlighted + auto-scrolled), and symbol search (ranked,
  match-type badges) all render and navigate correctly.

## Definition of Done

- [x] Keyword, symbol, and hybrid search work from the browser.
- [x] Files and their symbols are browsable.
- [x] Any result opens the source at its location, highlighted.
- [x] Gate green (types, lint, tests).

## Next (U4)

Interactive graph explorer (neighborhood around a symbol via `/api/graph`).
