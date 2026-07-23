# Phase 13 — Repository Intelligence

## What was built

`code-intel intel <path>` — a findings report over the repository: code smells,
anti-patterns, hotspots, and (when enrichment exists) domain/layer structure.
Findings are persisted and **diffable between runs**.

### Modules

- `intelligence/report.py` — `IntelligenceEngine` → `IntelligenceReport`.
- `intelligence/patterns.py` — `PatternDetector` (see Phase 21).

## Findings produced

| Category | Basis | Origin |
|----------|-------|--------|
| `circular_dependency` | module import cycles | STATIC_ANALYSIS |
| `duplicate_logic` | identical symbol code hash | STATIC_ANALYSIS |
| `dead_code` | callables with 0 inbound calls | STATIC_ANALYSIS |
| `hotspot` | most-called symbols | STATIC_ANALYSIS |
| `god_object` / `large_class` / `utility_abuse` | class structure | STATIC_ANALYSIS |
| `design_pattern` | naming/structure heuristics | STATIC_ANALYSIS |
| `long_function` | function length | STATIC_ANALYSIS |
| `business_domain` / `architecture_layer` | enrichment aggregation | LLM_INFERENCE |

Every finding carries `origin` and `confidence`; deterministic and inferred
findings are never merged and can be filtered with `--origin`.

## Diffing runs

Findings are stored in the `findings` table (replaced atomically per run).
`--diff` compares the new run against the previously stored findings and reports
`+new / -resolved` by `(category, target, title)`.

## How to run

```bash
uv run code-intel intel /path/to/repo
uv run code-intel intel /path/to/repo --diff
uv run code-intel intel /path/to/repo --origin STATIC_ANALYSIS
```

## Definition of Done

- [x] A repository intelligence report can be generated and diffed between two
      indexing runs.
- [x] All findings carry `origin` + `confidence`, separable by origin.
- [x] Typed, `ruff`-clean, `mypy --strict`-clean; unit-tested.
- [x] CLI exposes the capability.
