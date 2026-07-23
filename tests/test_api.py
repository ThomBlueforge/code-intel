"""Tests for the FastAPI surface (Phase 15 + U1 browser-UI gap-closing).

All endpoints are namespaced under ``/api``. Index/update/enrich/embed are
background jobs: the POST returns a job snapshot and the client polls
``/api/jobs/{id}`` for completion.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from code_intel.api.app import create_app


@pytest.fixture
def client_and_repo(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "auth.py").write_text(
        "def authenticate(user):\n    return validate(user)\n\n"
        "def validate(user):\n    return True\n",
        encoding="utf-8",
    )
    # Keep each test's index and registry isolated in tmp.
    os.environ["CODE_INTEL_DB"] = str(tmp_path / "index.db")
    os.environ["CODE_INTEL_REGISTRY"] = str(tmp_path / "registry.json")
    try:
        yield TestClient(create_app()), str(repo)
    finally:
        os.environ.pop("CODE_INTEL_DB", None)
        os.environ.pop("CODE_INTEL_REGISTRY", None)


def _run_job(client: TestClient, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    resp = getattr(client, method)(url, **kwargs)
    assert resp.status_code == 200, resp.text
    job_id = resp.json()["id"]
    for _ in range(200):
        snapshot = client.get(f"/api/jobs/{job_id}").json()
        if snapshot["status"] in ("done", "error"):
            return snapshot
        time.sleep(0.02)
    raise AssertionError("job did not finish in time")


def _index(client: TestClient, repo: str) -> dict[str, Any]:
    snapshot = _run_job(client, "post", "/api/index", json={"path": repo})
    assert snapshot["status"] == "done", snapshot
    return snapshot["result"]


def test_health_unindexed_then_index(client_and_repo) -> None:
    client, repo = client_and_repo
    assert client.get("/api/health", params={"path": repo}).json()["status"] == "unindexed"
    result = _index(client, repo)
    assert result["added"] == 1  # one file (auth.py)
    assert result["symbols_total"] == 2  # two functions
    assert client.get("/api/health", params={"path": repo}).json()["status"] == "ok"


def test_index_job_reports_error_for_missing_path(client_and_repo) -> None:
    client, _ = client_and_repo
    resp = client.post("/api/index", json={"path": "/no/such/path"})
    assert resp.status_code == 400


def test_repos_lists_indexed_repository(client_and_repo) -> None:
    client, repo = client_and_repo
    _index(client, repo)
    repos = client.get("/api/repos").json()["repositories"]
    assert any(r["path"] == str(Path(repo).resolve()) and r["indexed"] for r in repos)


def test_symbol_and_graph(client_and_repo) -> None:
    client, repo = client_and_repo
    _index(client, repo)
    sym = client.get("/api/symbol", params={"path": repo, "query": "authenticate"}).json()
    assert any(r["name"] == "authenticate" for r in sym["results"])
    graph = client.get("/api/graph", params={"path": repo, "symbol": "authenticate"}).json()
    assert graph["focus"] == "authenticate"
    assert graph["nodes"]


def test_symbols_breakdown_and_per_file(client_and_repo) -> None:
    client, repo = client_and_repo
    _index(client, repo)
    breakdown = client.get("/api/symbols", params={"path": repo}).json()["breakdown"]
    assert breakdown.get("function") == 2
    per_file = client.get(
        "/api/symbols", params={"path": repo, "file": "auth.py"}
    ).json()["symbols"]
    assert {s["name"] for s in per_file} == {"authenticate", "validate"}


def test_files(client_and_repo) -> None:
    client, repo = client_and_repo
    _index(client, repo)
    files = client.get("/api/files", params={"path": repo}).json()["files"]
    assert any(f["path"] == "auth.py" and f["language"] == "Python" for f in files)


def test_file_source(client_and_repo) -> None:
    client, repo = client_and_repo
    _index(client, repo)
    body = client.get("/api/file", params={"path": repo, "file": "auth.py"}).json()
    assert any("def authenticate" in line for line in body["lines"])
    assert body["total_lines"] >= 4


def test_file_source_rejects_escape(client_and_repo) -> None:
    client, repo = client_and_repo
    _index(client, repo)
    resp = client.get("/api/file", params={"path": repo, "file": "../../etc/passwd"})
    assert resp.status_code == 400


def test_search_and_stats(client_and_repo) -> None:
    client, repo = client_and_repo
    _index(client, repo)
    search = client.post("/api/search", json={"path": repo, "keyword": "validate"}).json()
    assert any("validate" in m["text"] for m in search["matches"])
    stats = client.get("/api/stats", params={"path": repo}).json()
    assert stats["symbols"] >= 2
    assert "circular_dependencies" in stats


def test_retrieve(client_and_repo) -> None:
    client, repo = client_and_repo
    _index(client, repo)
    result = client.post(
        "/api/retrieve", json={"path": repo, "query": "authenticate"}
    ).json()
    assert any(r["name"] == "authenticate" for r in result["results"])


def test_impact(client_and_repo) -> None:
    client, repo = client_and_repo
    _index(client, repo)
    impact = client.get("/api/impact", params={"path": repo, "symbol": "validate"}).json()
    assert impact["targets"] >= 1
    assert any("authenticate" in caller for caller in impact["direct_callers"])


def test_intel(client_and_repo) -> None:
    client, repo = client_and_repo
    _index(client, repo)
    intel = client.get("/api/intel", params={"path": repo, "diff": True}).json()
    assert "count" in intel
    assert "diff" in intel


def test_ask_without_llm(client_and_repo) -> None:
    client, repo = client_and_repo
    _index(client, repo)
    ask = client.post(
        "/api/ask", json={"path": repo, "question": "authenticate", "use_llm": False}
    ).json()
    assert ask["used_llm"] is False
    assert ask["citations"]


def test_browse_lists_repo(client_and_repo) -> None:
    client, repo = client_and_repo
    _index(client, repo)
    parent = str(Path(repo).parent)
    listing = client.get("/api/browse", params={"dir": parent}).json()
    entry = next(e for e in listing["entries"] if e["name"] == "repo")
    assert entry["indexed"] is True


def test_delete_repo(client_and_repo) -> None:
    client, repo = client_and_repo
    _index(client, repo)
    resp = client.request("DELETE", "/api/repo", params={"path": repo})
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
    # The repository row is gone, so repo-scoped endpoints 404 and it is unlisted.
    assert client.get("/api/symbol", params={"path": repo, "query": "x"}).status_code == 404
    repos = client.get("/api/repos").json()["repositories"]
    assert all(r["path"] != str(Path(repo).resolve()) for r in repos)


def test_unindexed_repo_404(client_and_repo) -> None:
    client, repo = client_and_repo
    assert client.get("/api/symbol", params={"path": repo, "query": "x"}).status_code == 404


def test_config(client_and_repo) -> None:
    client, repo = client_and_repo
    body = client.get("/api/config", params={"path": repo}).json()
    assert "llm" in body and "base_url" in body["llm"]
