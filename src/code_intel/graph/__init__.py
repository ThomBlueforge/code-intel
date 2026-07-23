"""Phase 3 — structural knowledge graph.

A directed multigraph of repository structure (repositories, files, symbols)
connected by deterministic ``STATIC_ANALYSIS`` edges. The concrete store lives
behind the ``GraphStore`` interface so a future Neo4j backend can replace
NetworkX without touching callers.
"""
