# Phase 6 — AI Enrichment

## What was built

The one layer where the LLM sees source. For each logical symbol it produces an
`EnrichedSymbol` — summary, business domain, architecture layer,
responsibilities, quality metrics, risks, technical debt, confidence — stored in
a **separate** table (`enriched_symbols`) joinable to the deterministic symbol
by `symbol_id`. Enrichment never alters structural facts, and every earlier
phase runs with this layer disabled.

### Modules

| Module | Responsibility |
|--------|----------------|
| `llm/client.py` | `ChatClient` protocol + `OpenAICompatibleClient` (Phase 17); fully configurable, retrying HTTP client. |
| `enrichment/prompts.py` | Controlled ontology + prompt builder demanding strict JSON. |
| `enrichment/enricher.py` | Calls the model, parses defensively, coerces to ontology, persists. |
| `storage/repositories.py` | `EnrichedSymbolStore` (upsert/get/count/enriched_ids). |

## No-hallucination guarantees

- The prompt forbids prose/markdown and requires `Unknown` + lowered confidence
  when unsure.
- Parsing is defensive: non-JSON, wrong types, or endpoint failure degrade to an
  explicit `summary="Unknown", confidence=0.0` record rather than a guess.
- Classifications are re-validated against the closed vocabularies
  (architecture layer / business domain / responsibilities); out-of-vocabulary
  labels are dropped, never invented.
- Quality metrics and confidence are clamped to `[0, 1]`.

## Configuration (no vendor lock-in)

All LLM parameters come from `LLMSettings` (base URL, api key, model,
temperature, max tokens, timeout, retries) — nothing hardcoded. Point it at any
OpenAI-compatible endpoint:

```bash
uv run code-intel enrich /path/to/repo \
  --base-url http://localhost:5000/v1 --model my-local-model --limit 50
```

The enricher takes a `ChatClient`, so tests inject a fake and need no network;
the CLI injects the real `OpenAICompatibleClient`.

## How to run

```bash
# Requires a running OpenAI-compatible endpoint (e.g. Text Generation Web UI).
uv run code-intel enrich /path/to/repo --limit 20
```

## Design notes

- Enriches logical units (`function`, `method`, `class`, `interface`, `struct`,
  `trait`, `enum`); constants/globals are skipped.
- Incremental: symbols already enriched are skipped unless `--force`.
- Sequential for now; batch size / concurrency knobs exist in `LLMSettings`
  and are wired in Phase 18.

## Definition of Done

- [x] Enrichment runs against real symbols via the configured OpenAI-compatible
      client and persists to `enriched_symbols`, joinable by `symbol_id`.
- [x] Separate from deterministic facts; symbols untouched (tested).
- [x] Explicit uncertainty (`Unknown`, confidence) instead of guessing (tested).
- [x] Typed, `ruff`-clean, `mypy --strict`-clean.
- [x] Unit tests with a fake client: ontology coercion, persistence/join,
      malformed-response degradation, skip/force, layer independence.
- [x] This doc; CLI exposes the capability.
