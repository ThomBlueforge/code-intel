"""Phases 13 & 21 — repository intelligence and pattern detection.

Detects code smells, anti-patterns, design patterns, hotspots, and (from
enrichment) domain/layer structure. Every finding carries an ``origin``
(STATIC_ANALYSIS vs LLM_INFERENCE) and a ``confidence`` so deterministic and
inferred results stay separable and are never silently merged. Findings are
persisted so two indexing runs can be diffed.
"""
