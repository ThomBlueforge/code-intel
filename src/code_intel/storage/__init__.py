"""Persistence layer: SQLite metadata and deterministic relational facts.

The storage boundary is strict — this package owns SQLite only. Graph data
(NetworkX) and embeddings (Qdrant) live in their own packages and are never
stored here.
"""
