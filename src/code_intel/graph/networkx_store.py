"""NetworkX-backed implementation of ``GraphStore``.

Uses a ``MultiDiGraph`` so multiple typed edges may connect the same pair of
nodes. Parallel edges of the *same* type between the same nodes are collapsed
(the edge key is the type) to keep the graph idempotent across rebuilds.
"""

from __future__ import annotations

from collections import deque

import networkx as nx

from code_intel.graph.interface import GraphEdge, GraphNode, GraphStore, Neighborhood


class NetworkXGraphStore(GraphStore):
    """In-memory structural graph."""

    def __init__(self) -> None:
        self._g: nx.MultiDiGraph = nx.MultiDiGraph()

    def add_node(self, node: GraphNode) -> None:
        self._g.add_node(node.id, kind=node.kind, name=node.name, attrs=dict(node.attrs))

    def add_edge(self, edge: GraphEdge) -> None:
        # Ensure endpoints exist so a partial build never raises on lookup.
        for endpoint in (edge.source, edge.target):
            if endpoint not in self._g:
                self._g.add_node(endpoint, kind="unknown", name=endpoint, attrs={})
        self._g.add_edge(
            edge.source,
            edge.target,
            key=edge.type,
            type=edge.type,
            origin=edge.origin,
            confidence=edge.confidence,
        )

    def has_node(self, node_id: str) -> bool:
        return node_id in self._g

    def get_node(self, node_id: str) -> GraphNode | None:
        if node_id not in self._g:
            return None
        data = self._g.nodes[node_id]
        return GraphNode(
            id=node_id,
            kind=data.get("kind", "unknown"),
            name=data.get("name", node_id),
            attrs=dict(data.get("attrs", {})),
        )

    def successors(self, node_id: str) -> list[GraphEdge]:
        if node_id not in self._g:
            return []
        return [
            _to_edge(node_id, target, data)
            for _s, target, data in self._g.out_edges(node_id, data=True)
        ]

    def predecessors(self, node_id: str) -> list[GraphEdge]:
        if node_id not in self._g:
            return []
        return [
            _to_edge(source, node_id, data)
            for source, _t, data in self._g.in_edges(node_id, data=True)
        ]

    def neighborhood(self, node_id: str, depth: int = 1) -> Neighborhood:
        if node_id not in self._g:
            return Neighborhood(focus=node_id, nodes=[], edges=[])

        visited: set[str] = {node_id}
        frontier: deque[tuple[str, int]] = deque([(node_id, 0)])
        while frontier:
            current, dist = frontier.popleft()
            if dist >= depth:
                continue
            for neighbour in set(self._g.successors(current)) | set(self._g.predecessors(current)):
                if neighbour not in visited:
                    visited.add(neighbour)
                    frontier.append((neighbour, dist + 1))

        nodes = [n for n in (self.get_node(i) for i in visited) if n is not None]
        edges: list[GraphEdge] = []
        for source, target, data in self._g.edges(data=True):
            if source in visited and target in visited:
                edges.append(_to_edge(source, target, data))
        return Neighborhood(focus=node_id, nodes=nodes, edges=edges)

    def in_degree(self, node_id: str) -> int:
        return int(self._g.in_degree(node_id)) if node_id in self._g else 0

    def out_degree(self, node_id: str) -> int:
        return int(self._g.out_degree(node_id)) if node_id in self._g else 0

    @property
    def node_count(self) -> int:
        return int(self._g.number_of_nodes())

    @property
    def edge_count(self) -> int:
        return int(self._g.number_of_edges())

    # --- Extension point for Phase 5 (dependency analysis) ---------------

    def raw(self) -> nx.MultiDiGraph:
        """Expose the underlying graph for read-only algorithm use.

        Intentionally narrow: analysis code (cycles, degrees) needs NetworkX
        algorithms. Mutation still goes through the typed ``GraphStore`` API.
        """
        return self._g


def _to_edge(source: str, target: str, data: dict[str, object]) -> GraphEdge:
    return GraphEdge(
        source=source,
        target=target,
        type=str(data.get("type", "")),
        origin=str(data.get("origin", "STATIC_ANALYSIS")),
        confidence=float(data.get("confidence", 1.0)),  # type: ignore[arg-type]
    )
