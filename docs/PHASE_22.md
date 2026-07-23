# Phase 22 — Change Impact Analysis

## What was built

`code-intel impact <symbol>` — given a symbol, what a change to it could touch:
direct callers, indirect (transitive) callers, affected files, affected modules,
and affected tests.

### Modules

- `dependencies/callgraph.py` — shared, reusable name-based call graph.
- `dependencies/impact.py` — `ImpactAnalyzer` + `ImpactReport`.

## Method

- **Direct callers** — inbound edges to any symbol with the given name.
- **Indirect callers** — the transitive reverse-call closure minus the direct
  set.
- **Affected files / modules** — paths (and their directories) of all callers.
- **Affected tests** — affected files whose path looks like a test
  (`test`/`spec`/`__tests__`).

## Nature of results

Resolution is **name-based** (shared with Phase 5), so results are candidates to
review, not proof — same-named symbols are treated as one target. Labelled as
heuristic in the CLI output.

## How to run

```bash
uv run code-intel impact processPayment --path .
```

## Definition of Done

- [x] Computes direct callers, indirect callers, affected files/modules, and
      affected tests for a symbol.
- [x] Reuses the shared call graph (no duplicated resolution logic).
- [x] Typed, `ruff`-clean, `mypy --strict`-clean; unit-tested.
- [x] CLI exposes the capability.
