"""Tests for dependency analysis and the stats report."""

from __future__ import annotations

from pathlib import Path

from code_intel.config import Settings
from code_intel.dependencies.analysis import DependencyAnalyzer
from code_intel.dependencies.relationships import RelationshipExtractor
from code_intel.ingestion.indexer import Indexer
from code_intel.storage.database import Database
from code_intel.storage.repositories import RepositoryStore


def test_relationship_extractor_calls_and_imports() -> None:
    rel = RelationshipExtractor()
    calls = rel.extract_call_names("Python", b"def f():\n    g()\n    obj.method()\n")
    assert "g" in calls
    assert "method" in calls
    imports = rel.extract_imports("Python", b"import os\nfrom a.b import c\n")
    assert set(imports) == {"os", "a.b"}


def _analyze(tmp_path: Path, files: dict[str, str]):
    repo = tmp_path / "repo"
    repo.mkdir()
    for rel, content in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    settings = Settings.for_repository(repo, db_path=tmp_path / "index.db")
    Indexer(settings).index(repo)
    with Database(settings.db_path) as db:
        conn = db.connection
        repo_row = RepositoryStore(conn).get_by_path(str(repo.resolve()))
        assert repo_row is not None
        return DependencyAnalyzer(conn, repo.resolve()).analyze(repo_row.id)


def test_call_graph_detects_dead_and_shared(tmp_path: Path) -> None:
    report = _analyze(
        tmp_path,
        {
            "app.py": (
                "def helper():\n    return 1\n\n"
                "def uses_helper():\n    return helper()\n\n"
                "def also_uses():\n    return helper()\n\n"
                "def never_called():\n    return 0\n"
            )
        },
    )
    assert report.call_edges >= 2
    # helper is called by two functions -> shared utility.
    shared = {name for name, _ in report.shared_utilities}
    assert "helper" in shared
    # never_called has no inbound calls -> dead-code candidate.
    assert any("never_called" in c for c in report.dead_code_candidates)
    # uses_helper is itself called by nobody, but calls helper -> also dead candidate.
    assert any("uses_helper" in c for c in report.dead_code_candidates)


def test_shared_utilities_suppresses_ambiguous_homonyms(tmp_path: Path) -> None:
    # Many classes each define a `get` method; name-based call resolution links
    # every `x.get()` to all of them, inflating each to an identical count.
    classes = "".join(
        f"class C{i}:\n"
        f"    def get(self):\n        return {i}\n\n"
        for i in range(6)
    )
    caller = "".join(
        f"def use{j}(c):\n    return c.get()\n\n" for j in range(8)
    )
    report = _analyze(tmp_path, {"m.py": classes + caller})
    shared = {name for name, _ in report.shared_utilities}
    # `get` is shared by 6 symbols -> ambiguous -> not reported as a hotspot,
    # and it must not appear as a wall of duplicate rows either.
    assert "get" not in shared
    names = [name for name, _ in report.shared_utilities]
    assert len(names) == len(set(names))  # one row per name, no duplicates


def test_duplicate_implementations_detected(tmp_path: Path) -> None:
    body = "def {name}():\n    x = 1\n    y = 2\n    z = 3\n    return x + y + z\n"
    report = _analyze(
        tmp_path,
        {"a.py": body.format(name="alpha"), "b.py": body.format(name="alpha")},
    )
    # Identical non-trivial bodies with the same name -> duplicate group.
    assert any(g.count >= 2 for g in report.duplicate_implementations)


def test_decorated_symbols_not_flagged_dead(tmp_path: Path) -> None:
    # A @property (attribute access) and a @app.command entrypoint have no
    # name-resolved callers, but decorators mark them as externally invoked.
    report = _analyze(
        tmp_path,
        {
            "m.py": (
                "import typer\n"
                "app = typer.Typer()\n\n"
                "class C:\n"
                "    @property\n"
                "    def size(self):\n        return 1\n\n"
                "@app.command()\n"
                "def serve():\n    return 0\n\n"
                "def orphan():\n    return 9\n"
            )
        },
    )
    dead = " ".join(report.dead_code_candidates)
    assert "size" not in dead  # @property
    assert "serve" not in dead  # @app.command
    assert "orphan" in dead  # undecorated, uncalled -> still dead


def test_reference_liveness_covers_jsx_props_and_members(tmp_path: Path) -> None:
    # `Button` is used only as JSX, `handler` only passed as a prop, `getRepos`
    # only as a member call — none are called by name, but all are referenced.
    lib = (
        "export function Button(props: object) {\n  return props;\n}\n"
        "export class Api {\n  getRepos() {\n    return [];\n  }\n}\n"
    )
    app = (
        "import { Button, Api } from './lib';\n"
        "function handler() {\n  return 1;\n}\n"
        "const api = new Api();\n"
        "export function App() {\n"
        "  api.getRepos();\n"
        "  return <Button onClick={handler} />;\n"
        "}\n"
        "function trulyDead() {\n  return 0;\n}\n"
    )
    report = _analyze(tmp_path, {"lib.tsx": lib, "app.tsx": app})
    dead = " ".join(report.dead_code_candidates)
    assert "Button" not in dead  # used as JSX
    assert "handler" not in dead  # passed as a prop
    assert "getRepos" not in dead  # member call
    assert "constructor" not in dead  # implicit via `new`
    assert "trulyDead" in dead  # defined, referenced nowhere -> dead


def test_module_import_graph_and_cycles(tmp_path: Path) -> None:
    report = _analyze(
        tmp_path,
        {
            "a.py": "import b\ndef fa():\n    return 1\n",
            "b.py": "import a\ndef fb():\n    return 2\n",
        },
    )
    assert report.import_edges == 2
    assert len(report.circular_dependencies) >= 1


def test_language_breakdown_and_counts(tmp_path: Path) -> None:
    report = _analyze(
        tmp_path,
        {"a.py": "def f():\n    return 1\n", "b.go": "package m\nfunc G() {}\n"},
    )
    assert report.files == 2
    assert report.languages.get("Python") == 1
    assert report.languages.get("Go") == 1
