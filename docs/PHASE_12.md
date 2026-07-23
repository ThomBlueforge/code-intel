# Phase 12 — AI Question Answering

## What was built

`code-intel ask "<question>"` — a grounded answer that cites the specific
symbols/files it used. The LLM never searches the repository; it only ever sees
a bounded context assembled by the hybrid retriever.

### Module

- `understanding/qa.py` — `QuestionAnswerer` + `Answer`.

## Flow

1. Retrieve the top symbols for the question (Phase 10 hybrid retriever —
   symbol + keyword + graph + optional vector).
2. Assemble a **bounded** context (capped symbols, capped code per symbol,
   capped total size) from each symbol's source + AI summary.
3. Ask the LLM to answer using only that context and cite `[n]` sources.
4. Return the answer plus citations back to the exact symbols used.

## Grounding & degradation

- The prompt restricts the model to the provided context and forbids invention.
- With `--no-llm`, or if the endpoint is unavailable, `ask` degrades to
  returning the ranked, cited context — still useful offline.

## How to run

```bash
uv run code-intel ask "How does authentication work?" --path .
uv run code-intel ask "Where is billing implemented?" --no-llm
```

## Definition of Done

- [x] `code-intel ask` returns a grounded answer citing the symbols/files used.
- [x] The LLM receives only assembled context, never the whole repository.
- [x] Degrades gracefully without an LLM.
- [x] Typed, `ruff`-clean, `mypy --strict`-clean; unit-tested with a fake client.
- [x] CLI exposes the capability.
