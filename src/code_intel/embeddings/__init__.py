"""Phase 7 — embedding pipeline.

Embeds complete logical units (never arbitrary text chunks). Runs after
enrichment so each embedded unit carries both deterministic facts and AI
understanding. The vector is handed to a ``VectorSink`` (Qdrant in Phase 8);
SQLite keeps only a traceability record so we can detect staleness.
"""
