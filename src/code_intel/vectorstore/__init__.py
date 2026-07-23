"""Phase 8 — vector database (Qdrant).

Persists embedding vectors and their payloads in an embedded, local Qdrant
instance (no server required). Owns exactly one kind of data: embeddings. The
structural graph is never stored here, and vectors are never stored in SQLite.
Implements the ``VectorSink`` protocol so the embedding pipeline writes to it
transparently.
"""
