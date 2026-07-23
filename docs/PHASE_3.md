# Phase 3 — Structural Knowledge Graph

## What was built

A directed multigraph of repository structure, projected deterministically from
the SQLite facts, behind a swappable `GraphStore` interface. `code-intel graph
<symbol>` returns the neighbourhood around a symbol.

### Modules

| Module | Responsibility |
|--------|----------------|
| `graph/interface.py` | `GraphStore` ABC + `GraphNode`/`GraphEdge`/`Neighborhood` types; origin constants. |
| `graph/networkx_store.py` | `NetworkXGraphStore` over `MultiDiGraph`; BFS neighbourhood, degrees. |
| `graph/builder.py` | Projects repositories/files/symbols into a graph of `contains` edges. |

## Graph model (Phase 3)

- **Nodes:** `repository`, `file`, and one per symbol (`class`, `function`,
  `method`, …), carrying name/path/language/visibility attributes.
- **Edges:** `contains` — repository→file, file→top-level-symbol,
  symbol→child-symbol (via `parent_id`). Every edge is
  `origin=STATIC_ANALYSIS, confidence=1.0`.
- Edges are idempotent per type: rebuilding never double-counts.

## Swappability

Callers depend only on `GraphStore`. A future `Neo4jGraphStore` implementing the
same ABC drops in without touching the builder, CLI, or later phases. The one
concession — `NetworkXGraphStore.raw()` — is a read-only escape hatch for
Phase 5 graph algorithms; all mutation still goes through the typed API.

## How to run

```bash
uv run code-intel graph Indexer --path .            # neighbourhood, depth 1
uv run code-intel graph Service --path . --depth 2
```

## Design notes

- The graph is built on demand from SQLite rather than persisted separately —
  it is a pure projection, so it can never drift from the facts. Persistence /
  incremental graph maintenance is Phase 16.
- Import/call/inherits edges are **not** here yet; they arrive in Phase 5, all
  still `STATIC_ANALYSIS`.

## Definition of Done

- [x] `code-intel graph <symbol>` returns a neighbourhood.
- [x] Storage behind an interface enabling a Neo4j swap without caller changes.
- [x] Typed, `ruff`-clean, `mypy --strict`-clean.
- [x] Unit tests: store operations, edge idempotency, depth-bounded
      neighbourhood, and builder projection of the contains hierarchy.
- [x] This doc; CLI exposes the capability.
