"""Phase 5 — dependency analysis.

Derives call and import relationships from deterministic facts and surfaces a
health report: call graph, module dependencies, circular dependencies, dead-code
candidates, orphan modules, entry points, shared utilities, and duplicate
implementations. Call resolution is name-based and therefore approximate; every
heuristic result is labelled as such.
"""
