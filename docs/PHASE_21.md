# Phase 21 — Ontology & Architectural Pattern Detection

*(Extends Phases 3 & 13 — does not re-derive facts already produced there.)*

## What was built

Design-pattern and anti-pattern detection over the deterministic symbol set,
surfaced through the Phase 13 `intel` report. Findings feed the same
`origin`+`confidence` model so inferred structure never merges with hard facts.

### Module

- `intelligence/patterns.py` — `PatternDetector` + `DetectedPattern`.

## Detected

**Design patterns** (naming/structure heuristics, modest confidence):
Repository, Factory, Builder, Strategy, Adapter, Observer, Facade, Service,
Singleton (instance-accessor method).

**Anti-patterns:** God Object (many methods / large LOC), Large Class, Utility
Class Abuse (`*Utils`/`*Helpers` collecting many methods). Circular
dependencies, duplicate logic, and dead code come from Phase 5 via the Phase 13
engine.

## Controlled ontology

The enrichment layer already classifies each symbol against the closed
vocabularies (architecture layer, business domain, responsibility) defined in
`enrichment/prompts.py`. Phase 13 aggregates those into `business_domain` /
`architecture_layer` findings tagged `LLM_INFERENCE`, giving a lightweight
context map of which domains and layers the code covers.

## Provenance discipline

- Pattern/anti-pattern findings are `STATIC_ANALYSIS` (naming/structure only).
- Domain/layer findings are `LLM_INFERENCE` (derived from enrichment).
- The two are stored side by side but always distinguishable by `origin`, per
  the non-negotiable "never merge inferred with static" rule.

## Scope & limitations

Pattern detection is intentionally conservative and naming-driven — a signal,
not proof (hence sub-0.7 confidence). Full behavioural pattern detection
(Strategy/Observer wiring, CQRS, Event Sourcing) and rich DDD bounded-context
mapping are future refinements; the current output covers the common,
high-signal cases.

## How to run

```bash
uv run code-intel intel /path/to/repo               # includes patterns
uv run code-intel intel /path/to/repo --origin LLM_INFERENCE   # domains/layers
```

## Definition of Done

- [x] Detects common design patterns and anti-patterns; stored with
      `origin`/`confidence`, never merged with static facts.
- [x] Aggregates the controlled ontology (domains/layers) from enrichment.
- [x] Typed, `ruff`-clean, `mypy --strict`-clean; unit-tested.
- [x] Exposed via `intel`.
