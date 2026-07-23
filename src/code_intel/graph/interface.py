"""Graph storage interface.

Defines the abstract contract every graph backend must satisfy. Calling code
(builder, dependency analysis, retrieval) depends only on ``GraphStore`` — never
on NetworkX or any other concrete engine — so the backend is swappable
(NetworkX now, Neo4j later) per the platform's non-negotiable principles.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

# Deterministic-vs-inferred provenance for every edge. Phase 3 emits only
# STATIC_ANALYSIS; LLM_INFERENCE edges (Phase 21) must stay separately filterable.
ORIGIN_STATIC = "STATIC_ANALYSIS"
ORIGIN_LLM = "LLM_INFERENCE"
ORIGIN_USER = "USER_DEFINED"


@dataclass(frozen=True)
class GraphNode:
    """A node in the structural graph."""

    id: str
    kind: str  # repository | file | function | method | class | ...
    name: str
    attrs: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphEdge:
    """A directed, typed, provenance-tagged edge."""

    source: str
    target: str
    type: str  # contains | calls | imports | inherits | ...
    origin: str = ORIGIN_STATIC
    confidence: float = 1.0


@dataclass(frozen=True)
class Neighborhood:
    """A subgraph around a focus node: the node, its neighbours, and edges."""

    focus: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class GraphStore(ABC):
    """Abstract structural graph. Implementations must be deterministic."""

    @abstractmethod
    def add_node(self, node: GraphNode) -> None: ...

    @abstractmethod
    def add_edge(self, edge: GraphEdge) -> None: ...

    @abstractmethod
    def has_node(self, node_id: str) -> bool: ...

    @abstractmethod
    def get_node(self, node_id: str) -> GraphNode | None: ...

    @abstractmethod
    def successors(self, node_id: str) -> list[GraphEdge]:
        """Outgoing edges from ``node_id``."""

    @abstractmethod
    def predecessors(self, node_id: str) -> list[GraphEdge]:
        """Incoming edges to ``node_id``."""

    @abstractmethod
    def neighborhood(self, node_id: str, depth: int = 1) -> Neighborhood:
        """Undirected BFS neighbourhood up to ``depth`` hops."""

    @abstractmethod
    def in_degree(self, node_id: str) -> int: ...

    @abstractmethod
    def out_degree(self, node_id: str) -> int: ...

    @property
    @abstractmethod
    def node_count(self) -> int: ...

    @property
    @abstractmethod
    def edge_count(self) -> int: ...
