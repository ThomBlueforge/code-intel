"""Phase 6 — AI enrichment.

The only place the LLM sees source code. Enrichment produces understanding
(summaries, domains, responsibilities, quality estimates, risks) that
references deterministic symbols by id and never overrides structural facts.
The enricher explicitly emits low confidence and "Unknown" rather than
guessing. This whole layer is optional: with it disabled, every earlier phase
still works.
"""
