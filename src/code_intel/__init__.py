"""Code Intelligence Platform.

A local-first system that ingests software repositories and produces a
queryable knowledge base combining deterministic static analysis with an
optional AI enrichment layer.

Architectural invariant: the deterministic layer (parsing, symbols, graph)
and the AI enrichment layer are always kept separate. Deterministic analysis
must remain fully functional with AI enrichment disabled.
"""

__version__ = "0.1.0"
