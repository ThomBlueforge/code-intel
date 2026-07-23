# Phase U4 — Interactive graph explorer

Adds a visual explorer for the structural graph, over the existing `/api/graph`
neighbourhood endpoint (no backend changes).

## What was built

- **`web/lib/graphLayout.ts`** — a small deterministic force-directed layout
  (Fruchterman–Reingold-ish): repulsion between all nodes, attraction along
  edges, the focus node pinned to centre. A few hundred synchronous iterations,
  no graph library.
- **`web/components/Graph.tsx`** — the explorer:
  - Symbol input + depth selector (1–3) → `getGraph(path, symbol, depth)`.
  - SVG canvas with **pan** (drag), **zoom** (non-passive wheel, so the page
    doesn't scroll), and **fit-to-bounds** (the neighbourhood auto-centres and
    scales into view on load).
  - Edges are coloured by **origin** — teal solid for `STATIC_ANALYSIS`, violet
    dashed for `LLM_INFERENCE` — with a legend; hovering a node highlights its
    incident edges.
  - The focus node is accent-filled and bold; **clicking any node refocuses**
    the graph on it (re-queries at the current depth).
  - Footer reports node/edge counts and the current focus.
- `app/page.tsx` enables the Graph nav item and renders `<Graph>` for the active
  repository.

## Notes

- Provenance is visible in the edges themselves, consistent with the rest of the
  UI: deterministic `contains`/call edges vs any inferred edges are never merged
  visually.
- Layout runs on the client; neighbourhoods are small, so it stays cheap
  (iterations are reduced above ~80 nodes). Dense neighbourhoods crowd labels at
  the default zoom — zoom/pan resolve it.

## Verification

- `pnpm typecheck` + `next build` clean; export synced to `src/code_intel/webui/`.
- Python gate unchanged: `ruff` + `mypy --strict` clean, 138 tests pass (no
  backend changes in this phase).
- Visual check against a live index: `HybridRetriever` at depth 2 renders a
  centred, fitted neighbourhood (29 nodes / 28 edges) with origin-coloured edges;
  zoom, pan, and click-to-refocus all work.

## Definition of Done

- [x] A symbol's neighbourhood renders as an interactive graph.
- [x] Depth is adjustable; nodes are clickable to refocus.
- [x] Edge origin (static vs llm) is visually distinct.
- [x] Pan/zoom/fit work; gate green.

## Next (U5)

Ask (grounded Q&A with citations), explain, impact, and the intelligence
findings view.
