"""HTTP routes for the Code Intelligence Platform.

Every capability the CLI exposes is reachable here as a thin adapter over the
same library code — no analysis logic lives in this module. Routes are namespaced
under ``/api`` so the static browser UI can own the rest of the URL space.

Long-running operations (index, update, enrich, embed) are submitted to the
background :class:`JobManager` and return a job snapshot; the client polls
``/api/jobs/{id}`` for progress and the final result. All other endpoints are
synchronous reads.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request

from code_intel.api.deps import (
    AskBody,
    EmbedBody,
    EnrichBody,
    PathBody,
    RetrieveBody,
    SearchBody,
    browse_directory,
    open_repo,
    read_file_snippet,
    settings_for,
)
from code_intel.api.jobs import JobManager, ProgressUpdate
from code_intel.dependencies.analysis import DependencyAnalyzer
from code_intel.dependencies.impact import ImpactAnalyzer
from code_intel.embeddings.pipeline import EmbeddingPipeline
from code_intel.embeddings.provider import HashingEmbeddingProvider
from code_intel.enrichment.enricher import Enricher
from code_intel.graph.builder import GraphBuilder
from code_intel.ingestion.indexer import Indexer
from code_intel.intelligence.report import IntelligenceEngine
from code_intel.keyword_search.searcher import KeywordSearcher
from code_intel.llm.client import OpenAICompatibleClient
from code_intel.models import Finding, Symbol
from code_intel.registry import RepositoryRegistry
from code_intel.retrieval.hybrid import HybridRetriever
from code_intel.storage.database import Database
from code_intel.storage.repositories import (
    EmbeddingStore,
    EnrichedSymbolStore,
    FileStore,
    FileUnderstandingStore,
    FindingStore,
    RepositoryStore,
    RepoUnderstandingStore,
    SymbolStore,
)
from code_intel.symbols.index import SymbolIndex
from code_intel.understanding.comprehension import ComprehensionBuilder
from code_intel.understanding.qa import QuestionAnswerer
from code_intel.understanding.summaries import SummaryBuilder
from code_intel.vectorstore.qdrant_store import QdrantVectorStore

router = APIRouter(prefix="/api")


def _jobs(request: Request) -> JobManager:
    """Typed accessor for the app-scoped background job manager."""
    return cast(JobManager, request.app.state.jobs)


# --- repositories & lifecycle ---------------------------------------------


@router.get("/repos")
def repos() -> dict[str, Any]:
    """List repositories that have been indexed (from the user registry)."""
    return {
        "repositories": [
            {
                "path": e.path,
                "name": e.name,
                "db_path": e.db_path,
                "last_indexed": e.last_indexed,
                "indexed": Path(e.db_path).exists(),
            }
            for e in RepositoryRegistry().list()
        ]
    }


@router.get("/browse")
def browse(dir: str | None = None) -> dict[str, Any]:
    """List sub-directories for the repo picker (directories only)."""
    return browse_directory(dir)


@router.get("/health")
def health(path: str) -> dict[str, Any]:
    settings = settings_for(path)
    if not settings.db_path.exists():
        return {"status": "unindexed", "db": str(settings.db_path)}
    with Database(settings.db_path) as db:
        version = db.connection.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()
        files = db.connection.execute("SELECT COUNT(*) AS n FROM files").fetchone()["n"]
    return {"status": "ok", "schema": version["value"], "files": files}


@router.get("/config")
def config(path: str = ".") -> dict[str, Any]:
    settings = settings_for(path)
    llm = settings.llm
    return {
        "db_path": str(settings.db_path),
        "max_file_bytes": settings.scan.max_file_bytes,
        "llm": {
            "base_url": llm.base_url,
            "model": llm.model,
            "temperature": llm.temperature,
            "max_tokens": llm.max_tokens,
            "max_retries": llm.max_retries,
            "batch_size": llm.batch_size,
            "max_concurrency": llm.max_concurrency,
        },
    }


def _submit_index(request: Request, path: str, kind: str) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        raise HTTPException(status_code=400, detail=f"Path does not exist: {path}")

    def run(update: ProgressUpdate) -> dict[str, Any]:
        settings = settings_for(path)
        report = Indexer(settings).index(
            target, progress=lambda done, rel: update(done, None, rel)
        )
        resolved = target.resolve()
        RepositoryRegistry().record(
            repo_path=resolved, name=resolved.name, db_path=settings.db_path
        )
        # Deterministic comprehension so file/repo understanding exists without an
        # LLM; `enrich` upgrades it to richer AI synthesis later.
        update(report.symbols_total, None, "Building codebase comprehension")
        with Database(settings.db_path) as store:
            ComprehensionBuilder(store.connection, report.repository_id).build()
        return {
            "repository_id": report.repository_id,
            "added": report.added,
            "changed": report.changed,
            "unchanged": report.unchanged,
            "removed": report.removed,
            "symbols_total": report.symbols_total,
        }

    return _jobs(request).submit(kind, run).snapshot()


@router.post("/index")
def index(body: PathBody, request: Request) -> dict[str, Any]:
    return _submit_index(request, body.path, "index")


@router.post("/update")
def update(body: PathBody, request: Request) -> dict[str, Any]:
    return _submit_index(request, body.path, "update")


@router.delete("/repo")
def delete_repo(path: str) -> dict[str, Any]:
    with open_repo(path) as (conn, repo), conn:
        conn.execute("DELETE FROM repositories WHERE id = ?", (repo.id,))
    RepositoryRegistry().remove(Path(path).resolve())
    return {"deleted": True, "path": str(Path(path).resolve())}


@router.get("/jobs")
def jobs(request: Request) -> dict[str, Any]:
    return {"jobs": [j.snapshot() for j in _jobs(request).list()]}


@router.get("/jobs/{job_id}")
def job(job_id: str, request: Request) -> dict[str, Any]:
    found = _jobs(request).get(job_id)
    if found is None:
        raise HTTPException(status_code=404, detail="No such job")
    return found.snapshot()


# --- search, symbols, graph, files ----------------------------------------


@router.post("/search")
def search(body: SearchBody) -> dict[str, Any]:
    repo_path = Path(body.path).resolve()
    with open_repo(body.path) as (conn, repo):
        files = FileStore(conn).list_records(repo.id)
    searcher = KeywordSearcher(repo_path, files)
    matches = searcher.search(
        body.keyword,
        regex=body.regex,
        case_sensitive=body.case_sensitive,
        languages=body.languages,
        limit=body.limit,
    )
    return {
        "backend": searcher.backend_name,
        "matches": [
            {"path": m.path, "line": m.line_number, "text": m.line} for m in matches
        ],
    }


@router.get("/symbol")
def symbol(path: str, query: str, limit: int = 20) -> dict[str, Any]:
    with open_repo(path) as (conn, repo):
        hits = SymbolIndex(conn).search(repo.id, query, limit=limit)
    return {
        "results": [
            {
                "name": h.name,
                "type": h.type,
                "path": h.path,
                "line": h.start_line,
                "score": h.score,
                "match": h.match_type,
            }
            for h in hits
        ]
    }


@router.get("/files")
def files(path: str) -> dict[str, Any]:
    with open_repo(path) as (conn, repo):
        records = FileStore(conn).list_records(repo.id)
    return {
        "files": [{"path": r.path, "language": r.language} for r in records],
    }


@router.get("/symbols")
def symbols(path: str, file: str | None = None) -> dict[str, Any]:
    with open_repo(path) as (conn, repo):
        if file is not None:
            rows = SymbolStore(conn).list_for_path(repo.id, file)
            names = {s.id: s.name for s in rows}
            return {
                "file": file,
                "symbols": [
                    {
                        "id": s.id,
                        "name": s.name,
                        "type": s.type,
                        "visibility": s.visibility,
                        "start_line": s.start_line,
                        "end_line": s.end_line,
                        "signature": s.signature,
                        "parent": names.get(s.parent_id) if s.parent_id else None,
                    }
                    for s in rows
                ],
            }
        breakdown = conn.execute(
            "SELECT type, COUNT(*) AS n FROM symbols WHERE repository_id = ? "
            "GROUP BY type ORDER BY n DESC",
            (repo.id,),
        ).fetchall()
        return {"breakdown": {row["type"]: row["n"] for row in breakdown}}


_SYMBOL_SORTS = frozenset({"loc", "name", "type", "path", "updated"})
_MAX_SYMBOL_LIMIT = 2000


def _symbol_detail(
    sym: Symbol, names: dict[str, str], enriched: dict[str, Any]
) -> dict[str, Any]:
    """Every stored field for a symbol, its length, and its enrichment if any."""
    e = enriched.get(sym.id)
    return {
        "id": sym.id,
        "name": sym.name,
        "type": sym.type,
        "language": sym.language,
        "path": sym.path,
        "start_line": sym.start_line,
        "end_line": sym.end_line,
        "loc": sym.end_line - sym.start_line + 1,
        "signature": sym.signature,
        "visibility": sym.visibility,
        "parent": names.get(sym.parent_id) if sym.parent_id else None,
        "decorators": list(sym.decorators),
        "code": sym.code,
        "hash": sym.hash,
        "created_at": sym.created_at,
        "updated_at": sym.updated_at,
        "enriched": asdict(e) if e is not None else None,
    }


@router.get("/symbols/all")
def all_symbols(
    path: str,
    q: str | None = None,
    sort: str = "loc",
    order: str = "desc",
    limit: int = 500,
) -> dict[str, Any]:
    """Repo-wide symbols with full fields, length (LOC), and enrichment.

    Searchable via ``q`` (name/type/path/signature/decorators) and sortable —
    default ``sort=loc order=desc`` surfaces the biggest symbols first.
    """
    sort = sort if sort in _SYMBOL_SORTS else "loc"
    reverse = order != "asc"
    needle = (q or "").strip().lower()
    limit = max(1, min(limit, _MAX_SYMBOL_LIMIT))

    with open_repo(path) as (conn, repo):
        symbols = SymbolStore(conn).list_for_repository(repo.id)
        names = {s.id: s.name for s in symbols}
        enriched = cast(dict[str, Any], EnrichedSymbolStore(conn).map_for_repository(repo.id))

    if needle:
        symbols = [s for s in symbols if _symbol_matches(s, needle)]

    if sort == "name":
        symbols.sort(key=lambda s: s.name.lower(), reverse=reverse)
    elif sort == "type":
        symbols.sort(key=lambda s: s.type, reverse=reverse)
    elif sort == "path":
        symbols.sort(key=lambda s: (s.path.lower(), s.start_line), reverse=reverse)
    elif sort == "updated":
        symbols.sort(key=lambda s: s.updated_at, reverse=reverse)
    else:  # loc
        symbols.sort(key=lambda s: s.end_line - s.start_line + 1, reverse=reverse)

    total = len(symbols)
    rows = symbols[:limit]
    return {
        "total": total,
        "returned": len(rows),
        "enriched_available": bool(enriched),
        "symbols": [_symbol_detail(s, names, enriched) for s in rows],
    }


def _symbol_matches(sym: Symbol, needle: str) -> bool:
    haystack = (
        f"{sym.name} {sym.type} {sym.language} {sym.path} "
        f"{sym.signature} {' '.join(sym.decorators)}"
    ).lower()
    return needle in haystack


@router.get("/graph")
def graph(path: str, symbol: str, depth: int = 1) -> dict[str, Any]:
    with open_repo(path) as (conn, repo):
        matches = SymbolStore(conn).find_by_name(repo.id, symbol)
        if not matches:
            raise HTTPException(status_code=404, detail=f"No symbol named {symbol}")
        store = GraphBuilder(conn).build(repo.id)
        hood = store.neighborhood(matches[0].id, depth=depth)
        nodes = [{"id": n.id, "kind": n.kind, "name": n.name} for n in hood.nodes]
        edges = [
            {"source": e.source, "target": e.target, "type": e.type, "origin": e.origin}
            for e in hood.edges
        ]
        focus = matches[0].name
    return {"focus": focus, "nodes": nodes, "edges": edges}


@router.get("/file")
def file_source(path: str, file: str, start: int = 1, end: int | None = None) -> dict[str, Any]:
    return read_file_snippet(path, file, start, end)


@router.post("/retrieve")
def retrieve(body: RetrieveBody) -> dict[str, Any]:
    settings = settings_for(body.path)
    repo_path = Path(body.path).resolve()
    provider = HashingEmbeddingProvider()
    qdrant_path = settings.db_path.parent / "qdrant"
    with open_repo(body.path) as (conn, repo):
        has_vectors = EmbeddingStore(conn).count() > 0 and qdrant_path.exists()
        vector_store = (
            QdrantVectorStore(qdrant_path, provider.dimension) if has_vectors else None
        )
        try:
            retriever = HybridRetriever(
                conn,
                repo.id,
                repo_path,
                vector_store=vector_store,
                embed_provider=provider if has_vectors else None,
            )
            results = retriever.retrieve(
                body.query, limit=body.limit, languages=body.languages, types=body.types
            )
        finally:
            if vector_store is not None:
                vector_store.close()
    return {
        "results": [
            {
                "name": r.name,
                "type": r.type,
                "path": r.path,
                "start_line": r.start_line,
                "score": r.score,
                "sources": r.sources,
            }
            for r in results
        ]
    }


# --- insights: stats, explain, impact, intelligence, ask ------------------


@router.get("/stats")
def stats(path: str) -> dict[str, Any]:
    repo_path = Path(path).resolve()
    with open_repo(path) as (conn, repo):
        report = DependencyAnalyzer(conn, repo_path).analyze(repo.id)
    return {
        "files": report.files,
        "symbols": report.symbols,
        "languages": report.languages,
        "call_edges": report.call_edges,
        "import_edges": report.import_edges,
        "circular_dependencies": report.circular_dependencies,
        "duplicate_implementations": [
            {"count": g.count, "names": g.names, "paths": g.paths}
            for g in report.duplicate_implementations
        ],
        "dead_code_candidates": report.dead_code_candidates,
        "orphan_modules": report.orphan_modules,
        "entry_points": report.entry_points,
        "shared_utilities": report.shared_utilities,
        "most_depended_modules": report.most_depended_modules,
    }


@router.get("/explain")
def explain(path: str, target: str) -> dict[str, Any]:
    with open_repo(path) as (conn, repo):
        explanation = SummaryBuilder(conn).explain(repo.id, target)
    if explanation is None:
        raise HTTPException(status_code=404, detail=f"Nothing to explain for {target}")
    return {
        "scope": explanation.scope,
        "target": explanation.target,
        "summary": explanation.summary,
        "details": explanation.details,
    }


@router.get("/understanding")
def understanding(path: str, file: str | None = None) -> dict[str, Any]:
    """Bottom-up comprehension: the repo overview and, if ``file`` is given, that
    file's holistic understanding (summary + enumerated responsibilities)."""
    with open_repo(path) as (conn, repo):
        repo_understanding = RepoUnderstandingStore(conn).get(repo.id)
        file_store = FileUnderstandingStore(conn)
        file_understanding = file_store.get(repo.id, file) if file else None
        file_count = file_store.count(repo.id)
    return {
        "available": repo_understanding is not None or file_count > 0,
        "repo": asdict(repo_understanding) if repo_understanding is not None else None,
        "file": asdict(file_understanding) if file_understanding is not None else None,
    }


@router.get("/impact")
def impact(path: str, symbol: str) -> dict[str, Any]:
    with open_repo(path) as (conn, repo):
        symbols_list = SymbolStore(conn).list_for_repository(repo.id)
    report = ImpactAnalyzer(symbols_list).impact(symbol)
    if report.targets == 0:
        raise HTTPException(status_code=404, detail=f"No symbol named {symbol}")
    return {
        "symbol": symbol,
        "targets": report.targets,
        "direct_callers": report.direct_callers,
        "indirect_callers": report.indirect_callers,
        "affected_files": report.affected_files,
        "affected_modules": report.affected_modules,
        "affected_tests": report.affected_tests,
    }


def _finding_key(finding: Finding) -> str:
    return f"{finding.category}|{finding.target}|{finding.title}"


def _finding_dict(finding: Finding) -> dict[str, Any]:
    return {
        "id": finding.id,
        "category": finding.category,
        "title": finding.title,
        "detail": finding.detail,
        "origin": finding.origin,
        "confidence": finding.confidence,
        "target": finding.target,
    }


@router.get("/intel")
def intel(path: str, origin: str | None = None, diff: bool = False) -> dict[str, Any]:
    repo_path = Path(path).resolve()
    with open_repo(path) as (conn, repo):
        finding_store = FindingStore(conn)
        previous = {_finding_key(f) for f in finding_store.list_for_repository(repo.id)}
        report = IntelligenceEngine(conn, repo_path).analyze(repo.id)
        finding_store.replace_all(repo.id, report.findings)
        conn.commit()
    findings = report.findings
    if origin is not None:
        findings = [f for f in findings if f.origin == origin]
    payload: dict[str, Any] = {
        "count": len(findings),
        "by_category": dict(report.by_category),
        "findings": [_finding_dict(f) for f in sorted(findings, key=lambda f: -f.confidence)],
    }
    if diff:
        current = {_finding_key(f) for f in report.findings}
        payload["diff"] = {
            "new": len(current - previous),
            "resolved": len(previous - current),
        }
    return payload


@router.post("/ask")
def ask(body: AskBody) -> dict[str, Any]:
    settings = settings_for(body.path)
    repo_path = Path(body.path).resolve()
    provider = HashingEmbeddingProvider()
    qdrant_path = settings.db_path.parent / "qdrant"
    chat = OpenAICompatibleClient(settings.llm) if body.use_llm else None
    with open_repo(body.path) as (conn, repo):
        has_vectors = EmbeddingStore(conn).count() > 0 and qdrant_path.exists()
        vector_store = (
            QdrantVectorStore(qdrant_path, provider.dimension) if has_vectors else None
        )
        try:
            retriever = HybridRetriever(
                conn,
                repo.id,
                repo_path,
                vector_store=vector_store,
                embed_provider=provider if has_vectors else None,
            )
            answer = QuestionAnswerer(conn, repo.id, retriever, chat_client=chat).ask(
                body.question
            )
        finally:
            if vector_store is not None:
                vector_store.close()
            if chat is not None:
                chat.close()
    return {
        "answer": answer.answer,
        "citations": answer.citations,
        "used_llm": answer.used_llm,
    }


# --- AI layers: enrich, embed (background jobs) ----------------------------


@router.post("/enrich")
def enrich(body: EnrichBody, request: Request) -> dict[str, Any]:
    settings = settings_for(body.path)
    if not settings.db_path.exists():
        raise HTTPException(status_code=404, detail="Repository not indexed")

    def run(update: ProgressUpdate) -> dict[str, Any]:
        llm = settings.llm
        if body.base_url is not None:
            llm = replace(llm, base_url=body.base_url)
        if body.model is not None:
            llm = replace(llm, model=body.model)
        client = OpenAICompatibleClient(llm)
        update(0, None, f"Enriching via {llm.base_url} (model={llm.model})")
        try:
            with Database(settings.db_path) as store:
                conn = store.connection
                repo = RepositoryStore(conn).get_by_path(str(Path(body.path).resolve()))
                if repo is None:
                    raise ValueError("Repository not indexed at this path")
                report = Enricher(conn, client, llm.model).enrich_repository(
                    repo.id, limit=body.limit, force=body.force
                )
                update(report.enriched, None, "Building codebase comprehension")
                comprehension = ComprehensionBuilder(conn, repo.id).build(
                    chat_client=client, model=llm.model, force=body.force
                )
        finally:
            client.close()
        return {
            "enriched": report.enriched,
            "skipped": report.skipped,
            "failed": report.failed,
            "total_enriched_in_repo": report.total_enriched_in_repo,
            "comprehension_files": comprehension.files_built,
            "comprehension_source": comprehension.source,
        }

    return _jobs(request).submit("enrich", run).snapshot()


@router.post("/embed")
def embed(body: EmbedBody, request: Request) -> dict[str, Any]:
    settings = settings_for(body.path)
    if not settings.db_path.exists():
        raise HTTPException(status_code=404, detail="Repository not indexed")

    def run(update: ProgressUpdate) -> dict[str, Any]:
        provider = HashingEmbeddingProvider()
        qdrant_path = settings.db_path.parent / "qdrant"
        update(0, None, "Embedding enriched symbols")
        with (
            Database(settings.db_path) as store,
            QdrantVectorStore(qdrant_path, provider.dimension) as vectors,
        ):
            conn = store.connection
            repo = RepositoryStore(conn).get_by_path(str(Path(body.path).resolve()))
            if repo is None:
                raise ValueError("Repository not indexed at this path")
            report = EmbeddingPipeline(conn, provider, "hashing-256").run(
                repo.id, vectors, limit=body.limit, force=body.force
            )
            vector_count = vectors.count()
        return {
            "embedded": report.embedded,
            "skipped": report.skipped,
            "dimension": report.dimension,
            "vectors_in_qdrant": vector_count,
        }

    return _jobs(request).submit("embed", run).snapshot()
