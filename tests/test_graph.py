"""Tests for the structural knowledge graph."""

from __future__ import annotations

from pathlib import Path

from code_intel.config import Settings
from code_intel.graph.builder import GraphBuilder
from code_intel.graph.interface import GraphEdge, GraphNode
from code_intel.graph.networkx_store import NetworkXGraphStore
from code_intel.ingestion.indexer import Indexer
from code_intel.storage.database import Database
from code_intel.storage.repositories import RepositoryStore, SymbolStore


def test_networkx_store_basic_operations() -> None:
    store = NetworkXGraphStore()
    store.add_node(GraphNode(id="a", kind="class", name="A"))
    store.add_node(GraphNode(id="b", kind="method", name="m"))
    store.add_edge(GraphEdge(source="a", target="b", type="contains"))
    assert store.has_node("a")
    assert store.node_count == 2
    assert store.edge_count == 1
    assert store.out_degree("a") == 1
    assert store.in_degree("b") == 1
    assert store.successors("a")[0].target == "b"
    assert store.predecessors("b")[0].source == "a"


def test_edges_are_idempotent_per_type() -> None:
    store = NetworkXGraphStore()
    edge = GraphEdge(source="a", target="b", type="contains")
    store.add_edge(edge)
    store.add_edge(edge)  # same type -> collapsed
    assert store.edge_count == 1


def test_neighborhood_respects_depth() -> None:
    store = NetworkXGraphStore()
    for nid in ("f", "c", "m", "x"):
        store.add_node(GraphNode(id=nid, kind="node", name=nid))
    store.add_edge(GraphEdge(source="f", target="c", type="contains"))
    store.add_edge(GraphEdge(source="c", target="m", type="contains"))
    store.add_edge(GraphEdge(source="m", target="x", type="calls"))

    depth1 = store.neighborhood("c", depth=1)
    assert {n.id for n in depth1.nodes} == {"f", "c", "m"}

    depth2 = store.neighborhood("c", depth=2)
    assert {n.id for n in depth2.nodes} == {"f", "c", "m", "x"}


def _index(tmp_path: Path, repo: Path) -> Settings:
    settings = Settings.for_repository(repo, db_path=tmp_path / "index.db")
    Indexer(settings).index(repo)
    return settings


def test_builder_projects_contains_hierarchy(sample_repo: Path, tmp_path: Path) -> None:
    (sample_repo / "mod.py").write_text(
        "class Service:\n    def run(self):\n        return 1\n", encoding="utf-8"
    )
    settings = _index(tmp_path, sample_repo)
    with Database(settings.db_path) as db:
        conn = db.connection
        repo = RepositoryStore(conn).get_by_path(str(sample_repo.resolve()))
        assert repo is not None
        graph = GraphBuilder(conn).build(repo.id)
        service, run = _named(conn, repo.id, "Service"), _named(conn, repo.id, "run")

    # repository -> file -> class -> method chain exists.
    assert graph.has_node(repo.id)
    assert graph.get_node(service).kind == "class"
    # The method's parent in the graph is the class.
    preds = graph.predecessors(run)
    assert any(e.source == service and e.type == "contains" for e in preds)
    # Every structural edge is deterministic.
    assert all(e.origin == "STATIC_ANALYSIS" for e in graph.successors(service))


def test_builder_neighborhood_of_class_reaches_methods(
    sample_repo: Path, tmp_path: Path
) -> None:
    (sample_repo / "svc.py").write_text(
        "class C:\n    def a(self):\n        return 1\n    def b(self):\n        return 2\n",
        encoding="utf-8",
    )
    settings = _index(tmp_path, sample_repo)
    with Database(settings.db_path) as db:
        conn = db.connection
        repo = RepositoryStore(conn).get_by_path(str(sample_repo.resolve()))
        assert repo is not None
        graph = GraphBuilder(conn).build(repo.id)
        cls = _named(conn, repo.id, "C")
        hood = graph.neighborhood(cls, depth=1)
    names = {n.name for n in hood.nodes}
    assert {"a", "b"}.issubset(names)


def _named(conn: object, repo_id: str, name: str) -> str:
    from sqlite3 import Connection

    assert isinstance(conn, Connection)
    return SymbolStore(conn).find_by_name(repo_id, name)[0].id
