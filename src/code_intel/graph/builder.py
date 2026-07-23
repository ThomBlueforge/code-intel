"""Builds the structural graph from deterministic SQLite facts.

Reads repositories, files, and symbols and materialises a ``GraphStore`` of
``contains`` relationships. This is a pure projection of already-persisted
facts — no parsing, no LLM. Import/call edges are layered on in Phase 5.
"""

from __future__ import annotations

import sqlite3

from code_intel.graph.interface import GraphEdge, GraphNode
from code_intel.graph.networkx_store import NetworkXGraphStore
from code_intel.storage.repositories import FileStore, RepositoryStore, SymbolStore


class GraphBuilder:
    """Projects SQLite facts into a structural graph."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def build(self, repository_id: str) -> NetworkXGraphStore:
        store = NetworkXGraphStore()
        file_store = FileStore(self._conn)
        symbol_store = SymbolStore(self._conn)

        repository = RepositoryStore(self._conn).get_by_id(repository_id)
        if repository is not None:
            store.add_node(
                GraphNode(id=repository.id, kind="repository", name=repository.name)
            )

        files = file_store.list_records(repository_id)
        for file in files:
            store.add_node(
                GraphNode(
                    id=file.id,
                    kind="file",
                    name=file.path,
                    attrs={"path": file.path, "language": file.language},
                )
            )
            store.add_edge(GraphEdge(source=repository_id, target=file.id, type="contains"))

        for symbol in symbol_store.list_for_repository(repository_id):
            store.add_node(
                GraphNode(
                    id=symbol.id,
                    kind=symbol.type,
                    name=symbol.name,
                    attrs={
                        "path": symbol.path,
                        "language": symbol.language,
                        "visibility": symbol.visibility,
                        "start_line": str(symbol.start_line),
                    },
                )
            )
            parent = symbol.parent_id if symbol.parent_id else symbol.file_id
            store.add_edge(GraphEdge(source=parent, target=symbol.id, type="contains"))

        return store
