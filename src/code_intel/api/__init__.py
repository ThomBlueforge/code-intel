"""Phase 15 — HTTP API (FastAPI).

A thin HTTP surface over the same library the CLI uses. Every endpoint takes a
repository ``path`` and operates on that repository's knowledge base. No
business logic lives here — endpoints are adapters.
"""
