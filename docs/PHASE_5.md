# Phase 5 — Dependency Analysis

## What was built

A dependency & health report surfaced by `code-intel stats`, derived from
deterministic facts: a call graph, a module dependency graph, and the findings
computed from them.

### Modules

| Module | Responsibility |
|--------|----------------|
| `dependencies/relationships.py` | Tree-sitter call/import queries (Python, JS, TS, Go). |
| `dependencies/analysis.py` | `DependencyAnalyzer` → `DependencyReport`. |

## What the report contains

| Finding | Basis | Nature |
|---------|-------|--------|
| File / symbol / language counts | SQLite | exact |
| Duplicate implementations | identical symbol code hash (≥ 2-line span) | exact |
| Call graph edges | callee-name → symbol resolution | approximate |
| Circular dependencies | cycles in the module import graph | exact given imports |
| Dead-code candidates | functions/methods with 0 inbound calls | heuristic |
| Orphan modules | files with 0 inbound imports, not entry points | heuristic |
| Entry points | symbols named `main` | heuristic |
| Shared utilities | most-called symbols | heuristic |
| Most-depended modules | highest inbound import count | exact given imports |

## Method

- **Call graph** is built from each symbol's stored source (no disk read).
  Resolution is **name-based**: a call to `foo` links to every symbol named
  `foo`. This over-links under name collisions and is labelled heuristic.
- **Module graph** re-reads each file from disk to extract imports, resolving
  intra-repo targets for Python (`a.b` → `a/b.py` | `a/b/__init__.py`) and
  relative JS/TS imports (`./x` → `x.ts|tsx|js|…|/index.*`). Bare/external
  imports are not graphed.
- Cycles via `networkx.simple_cycles`; dead code excludes dunder and
  `test*`-prefixed names and `main`.

## How to run

```bash
uv run code-intel stats /path/to/repo
uv run code-intel stats /path/to/repo --json
```

## Known limitations

- Call/import extraction is implemented for Python, JavaScript, TypeScript, and
  Go; other languages contribute no edges (counts/duplicates still work).
- Name-based call resolution cannot distinguish overloaded/same-named symbols;
  treat call-derived findings as candidates, not proof.
- "Unused exports" from the spec is approximated by dead-code candidates
  (export tracking arrives with the relationship persistence of later phases).

## Definition of Done

- [x] `code-intel stats` surfaces call graph, circular deps, dead-code
      candidates, orphan modules, entry points, shared utilities, duplicates.
- [x] Typed, `ruff`-clean, `mypy --strict`-clean.
- [x] Unit tests: relationship extraction, call graph (dead/shared),
      duplicates, import cycles, language breakdown.
- [x] This doc; CLI exposes the capability.
