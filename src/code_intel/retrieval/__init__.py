"""Phase 10 — hybrid retrieval.

A single ``retrieve(query)`` that draws from all five sources — symbol search,
keyword search, graph traversal, vector similarity, and metadata filtering —
then merges, deduplicates, and ranks. The vector source is optional: with no
embeddings/enrichment, retrieval still works from the deterministic sources.
"""
