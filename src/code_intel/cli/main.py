"""CLI entry point.

Phase 1 exposes ``index`` (run ingestion) and ``health`` (verify the store).
Later phases add ``search``, ``graph``, ``symbol``, ``ask``, ``stats``, etc.
Each command is a thin adapter over the library; no business logic lives here.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from code_intel import __version__
from code_intel.config import Settings
from code_intel.dependencies.analysis import DependencyAnalyzer, DependencyReport
from code_intel.dependencies.impact import ImpactAnalyzer
from code_intel.embeddings.pipeline import EmbeddingPipeline
from code_intel.embeddings.provider import HashingEmbeddingProvider
from code_intel.enrichment.enricher import Enricher
from code_intel.graph.builder import GraphBuilder
from code_intel.ingestion.indexer import Indexer, IndexReport
from code_intel.intelligence.report import IntelligenceEngine
from code_intel.keyword_search.searcher import KeywordSearcher
from code_intel.llm.client import OpenAICompatibleClient
from code_intel.models import Finding
from code_intel.registry import RepositoryRegistry
from code_intel.retrieval.hybrid import HybridRetriever
from code_intel.storage.database import Database
from code_intel.storage.repositories import (
    EmbeddingStore,
    FileStore,
    FindingStore,
    RepositoryStore,
    SymbolStore,
)
from code_intel.symbols.index import SymbolIndex
from code_intel.understanding.qa import QuestionAnswerer
from code_intel.understanding.summaries import SummaryBuilder
from code_intel.vectorstore.qdrant_store import QdrantVectorStore

app = typer.Typer(
    name="code-intel",
    help="Local-first Code Intelligence Platform.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


def _settings(path: Path, db: Path | None) -> Settings:
    return Settings.for_repository(path.resolve(), db_path=db)


@app.command()
def index(
    path: Annotated[Path, typer.Argument(help="Repository path to index.")],
    db: Annotated[
        Path | None,
        typer.Option("--db", help="Override the SQLite database path."),
    ] = None,
    as_json: Annotated[
        bool, typer.Option("--json", help="Emit the report as JSON.")
    ] = False,
    jobs: Annotated[
        int, typer.Option("--jobs", "-j", help="Parallel parsing workers.")
    ] = 1,
) -> None:
    """Index a repository, incrementally updating the file manifest."""
    if not path.exists():
        console.print(f"[red]Path does not exist:[/red] {path}")
        raise typer.Exit(code=2)

    settings = _settings(path, db)
    report = Indexer(settings).index(path, jobs=jobs)
    RepositoryRegistry().record(
        repo_path=path.resolve(), name=path.resolve().name, db_path=settings.db_path
    )

    if as_json:
        console.print_json(json.dumps(_report_dict(report, settings.db_path)))
        return
    _render_report(report, settings.db_path)


@app.command()
def health(
    path: Annotated[Path, typer.Argument(help="Repository path whose store to check.")],
    db: Annotated[
        Path | None, typer.Option("--db", help="Override the SQLite database path.")
    ] = None,
) -> None:
    """Verify the knowledge base for a repository is present and openable."""
    settings = _settings(path, db)
    if not settings.db_path.exists():
        console.print(f"[yellow]No index found at[/yellow] {settings.db_path}")
        raise typer.Exit(code=1)
    with Database(settings.db_path) as store:
        row = store.connection.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()
        files = store.connection.execute("SELECT COUNT(*) AS n FROM files").fetchone()["n"]
    console.print(
        f"[green]OK[/green]  db={settings.db_path}  schema=v{row['value']}  files={files}"
    )


@app.command()
def symbols(
    path: Annotated[Path, typer.Argument(help="Repository path.")],
    file: Annotated[
        str | None,
        typer.Option("--file", help="Repository-relative file path to list symbols for."),
    ] = None,
    db: Annotated[
        Path | None, typer.Option("--db", help="Override the SQLite database path.")
    ] = None,
) -> None:
    """List deterministic symbols for a file (or a repo-wide type breakdown)."""
    settings = _settings(path, db)
    if not settings.db_path.exists():
        console.print(f"[yellow]No index found at[/yellow] {settings.db_path}")
        raise typer.Exit(code=1)

    with Database(settings.db_path) as store:
        conn = store.connection
        repo = RepositoryStore(conn).get_by_path(str(path.resolve()))
        if repo is None:
            console.print("[yellow]Repository not indexed at this path.[/yellow]")
            raise typer.Exit(code=1)
        symbol_store = SymbolStore(conn)
        if file is not None:
            _render_symbols_for_file(symbol_store, repo.id, file)
        else:
            _render_symbol_breakdown(conn, repo.id)


@app.command()
def symbol(
    query: Annotated[str, typer.Argument(help="Symbol name (exact, prefix, or fuzzy).")],
    path: Annotated[Path, typer.Option("--path", help="Repository path.")] = Path("."),
    lang: Annotated[
        list[str] | None, typer.Option("--lang", help="Filter by language (repeatable).")
    ] = None,
    type_: Annotated[
        list[str] | None, typer.Option("--type", help="Filter by symbol type (repeatable).")
    ] = None,
    path_prefix: Annotated[
        str | None, typer.Option("--in", help="Restrict to a path prefix.")
    ] = None,
    limit: Annotated[int, typer.Option("--limit", help="Max results.")] = 20,
    db: Annotated[
        Path | None, typer.Option("--db", help="Override the SQLite database path.")
    ] = None,
) -> None:
    """Search symbols by name with ranked exact/prefix/fuzzy matching."""
    settings = _settings(path, db)
    if not settings.db_path.exists():
        console.print(f"[yellow]No index found at[/yellow] {settings.db_path}")
        raise typer.Exit(code=1)
    with Database(settings.db_path) as store:
        conn = store.connection
        repo = RepositoryStore(conn).get_by_path(str(path.resolve()))
        if repo is None:
            console.print("[yellow]Repository not indexed at this path.[/yellow]")
            raise typer.Exit(code=1)
        hits = SymbolIndex(conn).search(
            repo.id, query, languages=lang, types=type_, path_prefix=path_prefix, limit=limit
        )
    if not hits:
        console.print(f"[dim]No symbols matching[/dim] {query}")
        return
    table = Table(title=f"Symbol search: {query}", header_style="bold cyan")
    table.add_column("Score", justify="right")
    table.add_column("Match")
    table.add_column("Type")
    table.add_column("Name")
    table.add_column("Location")
    for hit in hits:
        table.add_row(
            f"{hit.score:.2f}",
            hit.match_type,
            hit.type,
            hit.name,
            f"{hit.path}:{hit.start_line}",
        )
    console.print(table)


@app.command()
def graph(
    symbol: Annotated[str, typer.Argument(help="Symbol name to focus the graph on.")],
    path: Annotated[Path, typer.Option("--path", help="Repository path.")] = Path("."),
    depth: Annotated[int, typer.Option("--depth", help="Neighbourhood hops.")] = 1,
    db: Annotated[
        Path | None, typer.Option("--db", help="Override the SQLite database path.")
    ] = None,
) -> None:
    """Show the structural graph neighbourhood around a symbol."""
    settings = _settings(path, db)
    if not settings.db_path.exists():
        console.print(f"[yellow]No index found at[/yellow] {settings.db_path}")
        raise typer.Exit(code=1)

    with Database(settings.db_path) as store:
        conn = store.connection
        repo = RepositoryStore(conn).get_by_path(str(path.resolve()))
        if repo is None:
            console.print("[yellow]Repository not indexed at this path.[/yellow]")
            raise typer.Exit(code=1)
        matches = SymbolStore(conn).find_by_name(repo.id, symbol)
        if not matches:
            console.print(f"[dim]No symbol named[/dim] {symbol}")
            raise typer.Exit(code=1)
        graph_store = GraphBuilder(conn).build(repo.id)

    focus = matches[0]
    if len(matches) > 1:
        console.print(
            f"[dim]{len(matches)} symbols named {symbol}; showing "
            f"{focus.path}:{focus.start_line}[/dim]"
        )
    hood = graph_store.neighborhood(focus.id, depth=depth)
    node_names = {n.id: n for n in hood.nodes}
    table = Table(title=f"Graph around {symbol} (depth {depth})", header_style="bold cyan")
    table.add_column("Relationship")
    table.add_column("From")
    table.add_column("Type")
    table.add_column("To")
    for edge in hood.edges:
        src = node_names.get(edge.source)
        tgt = node_names.get(edge.target)
        table.add_row(
            edge.type,
            f"{src.kind}:{src.name}" if src else edge.source[:8],
            edge.origin,
            f"{tgt.kind}:{tgt.name}" if tgt else edge.target[:8],
        )
    console.print(
        f"Focus: [bold]{focus.type} {focus.name}[/bold] "
        f"({focus.path}:{focus.start_line})  "
        f"nodes={len(hood.nodes)} edges={len(hood.edges)}"
    )
    console.print(table)


@app.command()
def stats(
    path: Annotated[Path, typer.Argument(help="Repository path.")],
    db: Annotated[
        Path | None, typer.Option("--db", help="Override the SQLite database path.")
    ] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Emit the report as JSON.")] = False,
) -> None:
    """Dependency & health report: cycles, dead code, duplicates, hotspots."""
    settings = _settings(path, db)
    if not settings.db_path.exists():
        console.print(f"[yellow]No index found at[/yellow] {settings.db_path}")
        raise typer.Exit(code=1)
    with Database(settings.db_path) as store:
        conn = store.connection
        repo = RepositoryStore(conn).get_by_path(str(path.resolve()))
        if repo is None:
            console.print("[yellow]Repository not indexed at this path.[/yellow]")
            raise typer.Exit(code=1)
        report = DependencyAnalyzer(conn, path.resolve()).analyze(repo.id)
    if as_json:
        console.print_json(json.dumps(_stats_dict(report)))
        return
    _render_stats(report)


@app.command()
def enrich(
    path: Annotated[Path, typer.Argument(help="Repository path.")],
    limit: Annotated[
        int | None, typer.Option("--limit", help="Max symbols to enrich this run.")
    ] = None,
    force: Annotated[
        bool, typer.Option("--force", help="Re-enrich symbols already enriched.")
    ] = False,
    base_url: Annotated[
        str | None, typer.Option("--base-url", help="Override LLM endpoint base URL.")
    ] = None,
    model: Annotated[
        str | None, typer.Option("--model", help="Override LLM model name.")
    ] = None,
    db: Annotated[
        Path | None, typer.Option("--db", help="Override the SQLite database path.")
    ] = None,
) -> None:
    """AI-enrich symbols via the configured local LLM (optional layer)."""
    settings = _settings(path, db)
    if not settings.db_path.exists():
        console.print(f"[yellow]No index found at[/yellow] {settings.db_path}")
        raise typer.Exit(code=1)

    llm = settings.llm
    if base_url is not None:
        llm = replace(llm, base_url=base_url)
    if model is not None:
        llm = replace(llm, model=model)

    client = OpenAICompatibleClient(llm)
    console.print(f"[dim]Enriching via {llm.base_url} (model={llm.model})…[/dim]")
    try:
        with Database(settings.db_path) as store:
            conn = store.connection
            repo = RepositoryStore(conn).get_by_path(str(path.resolve()))
            if repo is None:
                console.print("[yellow]Repository not indexed at this path.[/yellow]")
                raise typer.Exit(code=1)
            report = Enricher(conn, client, llm.model).enrich_repository(
                repo.id, limit=limit, force=force
            )
    finally:
        client.close()

    console.print(
        f"[green]Enriched[/green] {report.enriched}  "
        f"skipped {report.skipped}  failed {report.failed}  "
        f"total in repo {report.total_enriched_in_repo}"
    )


@app.command()
def embed(
    path: Annotated[Path, typer.Argument(help="Repository path.")],
    limit: Annotated[
        int | None, typer.Option("--limit", help="Max symbols to embed this run.")
    ] = None,
    force: Annotated[
        bool, typer.Option("--force", help="Re-embed unchanged symbols.")
    ] = False,
    db: Annotated[
        Path | None, typer.Option("--db", help="Override the SQLite database path.")
    ] = None,
) -> None:
    """Embed enriched symbols with the offline hashing provider into local Qdrant."""
    settings = _settings(path, db)
    if not settings.db_path.exists():
        console.print(f"[yellow]No index found at[/yellow] {settings.db_path}")
        raise typer.Exit(code=1)
    provider = HashingEmbeddingProvider()
    qdrant_path = settings.db_path.parent / "qdrant"
    with (
        Database(settings.db_path) as store,
        QdrantVectorStore(qdrant_path, provider.dimension) as vectors,
    ):
        conn = store.connection
        repo = RepositoryStore(conn).get_by_path(str(path.resolve()))
        if repo is None:
            console.print("[yellow]Repository not indexed at this path.[/yellow]")
            raise typer.Exit(code=1)
        report = EmbeddingPipeline(conn, provider, "hashing-256").run(
            repo.id, vectors, limit=limit, force=force
        )
        vector_count = vectors.count()
    console.print(
        f"[green]Embedded[/green] {report.embedded}  skipped {report.skipped}  "
        f"dim={report.dimension}  vectors in Qdrant {vector_count}"
    )


@app.command()
def search(
    keyword: Annotated[str, typer.Option("--keyword", help="Text or regex to search for.")],
    path: Annotated[Path, typer.Option("--path", help="Repository path.")] = Path("."),
    regex: Annotated[bool, typer.Option("--regex", help="Treat keyword as a regex.")] = False,
    case_sensitive: Annotated[
        bool, typer.Option("--case-sensitive", help="Match case exactly.")
    ] = False,
    lang: Annotated[
        list[str] | None, typer.Option("--lang", help="Filter by language (repeatable).")
    ] = None,
    context: Annotated[int, typer.Option("--context", "-C", help="Context lines.")] = 2,
    limit: Annotated[int, typer.Option("--limit", help="Max matches.")] = 50,
    db: Annotated[
        Path | None, typer.Option("--db", help="Override the SQLite database path.")
    ] = None,
) -> None:
    """Keyword/regex search across indexed files, with context."""
    settings = _settings(path, db)
    if not settings.db_path.exists():
        console.print(f"[yellow]No index found at[/yellow] {settings.db_path}")
        raise typer.Exit(code=1)
    with Database(settings.db_path) as store:
        conn = store.connection
        repo = RepositoryStore(conn).get_by_path(str(path.resolve()))
        if repo is None:
            console.print("[yellow]Repository not indexed at this path.[/yellow]")
            raise typer.Exit(code=1)
        files = FileStore(conn).list_records(repo.id)
    searcher = KeywordSearcher(path.resolve(), files)
    matches = searcher.search(
        keyword,
        regex=regex,
        case_sensitive=case_sensitive,
        languages=lang,
        context=context,
        limit=limit,
    )
    if not matches:
        console.print(f"[dim]No matches for[/dim] {keyword}")
        return
    console.print(f"[dim]{len(matches)} match(es) via {searcher.backend_name}[/dim]")
    for match in matches:
        console.print(f"[cyan]{match.path}:{match.line_number}[/cyan]")
        for line in match.before:
            console.print(f"  [dim]{line}[/dim]")
        console.print(f"  [bold]{match.line}[/bold]")
        for line in match.after:
            console.print(f"  [dim]{line}[/dim]")


@app.command()
def retrieve(
    query: Annotated[str, typer.Argument(help="Natural-language or code query.")],
    path: Annotated[Path, typer.Option("--path", help="Repository path.")] = Path("."),
    limit: Annotated[int, typer.Option("--limit", help="Max results.")] = 10,
    lang: Annotated[
        list[str] | None, typer.Option("--lang", help="Filter by language (repeatable).")
    ] = None,
    type_: Annotated[
        list[str] | None, typer.Option("--type", help="Filter by symbol type (repeatable).")
    ] = None,
    db: Annotated[
        Path | None, typer.Option("--db", help="Override the SQLite database path.")
    ] = None,
) -> None:
    """Hybrid retrieval across symbols, keywords, graph, and vectors."""
    settings = _settings(path, db)
    if not settings.db_path.exists():
        console.print(f"[yellow]No index found at[/yellow] {settings.db_path}")
        raise typer.Exit(code=1)

    provider = HashingEmbeddingProvider()
    qdrant_path = settings.db_path.parent / "qdrant"
    with Database(settings.db_path) as store:
        conn = store.connection
        repo = RepositoryStore(conn).get_by_path(str(path.resolve()))
        if repo is None:
            console.print("[yellow]Repository not indexed at this path.[/yellow]")
            raise typer.Exit(code=1)
        has_vectors = EmbeddingStore(conn).count() > 0 and qdrant_path.exists()
        vector_store = (
            QdrantVectorStore(qdrant_path, provider.dimension) if has_vectors else None
        )
        try:
            retriever = HybridRetriever(
                conn,
                repo.id,
                path.resolve(),
                vector_store=vector_store,
                embed_provider=provider if has_vectors else None,
            )
            results = retriever.retrieve(query, limit=limit, languages=lang, types=type_)
        finally:
            if vector_store is not None:
                vector_store.close()

    if not results:
        console.print(f"[dim]No results for[/dim] {query}")
        return
    table = Table(title=f"Retrieval: {query}", header_style="bold cyan")
    table.add_column("Score", justify="right")
    table.add_column("Type")
    table.add_column("Name")
    table.add_column("Sources")
    table.add_column("Location")
    for result in results:
        table.add_row(
            f"{result.score:.3f}",
            result.type,
            result.name,
            ",".join(result.sources),
            f"{result.path}:{result.start_line}",
        )
    console.print(table)


@app.command()
def explain(
    target: Annotated[str, typer.Argument(help="'.', a file/dir path, or a symbol name.")],
    path: Annotated[Path, typer.Option("--path", help="Repository path.")] = Path("."),
    db: Annotated[
        Path | None, typer.Option("--db", help="Override the SQLite database path.")
    ] = None,
) -> None:
    """Explain a symbol, module, package, or the whole repository."""
    settings = _settings(path, db)
    if not settings.db_path.exists():
        console.print(f"[yellow]No index found at[/yellow] {settings.db_path}")
        raise typer.Exit(code=1)
    with Database(settings.db_path) as store:
        conn = store.connection
        repo = RepositoryStore(conn).get_by_path(str(path.resolve()))
        if repo is None:
            console.print("[yellow]Repository not indexed at this path.[/yellow]")
            raise typer.Exit(code=1)
        explanation = SummaryBuilder(conn).explain(repo.id, target)
    if explanation is None:
        console.print(f"[dim]Nothing to explain for[/dim] {target}")
        raise typer.Exit(code=1)
    console.print(f"[bold cyan]{explanation.scope}[/bold cyan] {explanation.target}")
    console.print(explanation.summary)
    for detail in explanation.details[:20]:
        console.print(f"  [dim]{detail}[/dim]")


@app.command()
def ask(
    question: Annotated[str, typer.Argument(help="A question about the repository.")],
    path: Annotated[Path, typer.Option("--path", help="Repository path.")] = Path("."),
    no_llm: Annotated[
        bool, typer.Option("--no-llm", help="Skip the LLM; return cited context only.")
    ] = False,
    base_url: Annotated[
        str | None, typer.Option("--base-url", help="Override LLM endpoint base URL.")
    ] = None,
    model: Annotated[str | None, typer.Option("--model", help="Override LLM model.")] = None,
    db: Annotated[
        Path | None, typer.Option("--db", help="Override the SQLite database path.")
    ] = None,
) -> None:
    """Answer a question, grounded in retrieved context, with citations."""
    settings = _settings(path, db)
    if not settings.db_path.exists():
        console.print(f"[yellow]No index found at[/yellow] {settings.db_path}")
        raise typer.Exit(code=1)

    provider = HashingEmbeddingProvider()
    qdrant_path = settings.db_path.parent / "qdrant"
    chat = None
    if not no_llm:
        llm = settings.llm
        if base_url is not None:
            llm = replace(llm, base_url=base_url)
        if model is not None:
            llm = replace(llm, model=model)
        chat = OpenAICompatibleClient(llm)

    with Database(settings.db_path) as store:
        conn = store.connection
        repo = RepositoryStore(conn).get_by_path(str(path.resolve()))
        if repo is None:
            console.print("[yellow]Repository not indexed at this path.[/yellow]")
            raise typer.Exit(code=1)
        has_vectors = EmbeddingStore(conn).count() > 0 and qdrant_path.exists()
        vector_store = (
            QdrantVectorStore(qdrant_path, provider.dimension) if has_vectors else None
        )
        try:
            retriever = HybridRetriever(
                conn,
                repo.id,
                path.resolve(),
                vector_store=vector_store,
                embed_provider=provider if has_vectors else None,
            )
            answer = QuestionAnswerer(conn, repo.id, retriever, chat_client=chat).ask(question)
        finally:
            if vector_store is not None:
                vector_store.close()
            if chat is not None:
                chat.close()

    console.print(answer.answer)
    if answer.citations:
        console.print("\n[bold]Sources:[/bold]")
        for citation in answer.citations:
            console.print(f"  [dim]{citation}[/dim]")


@app.command()
def impact(
    symbol: Annotated[str, typer.Argument(help="Symbol name to analyse impact for.")],
    path: Annotated[Path, typer.Option("--path", help="Repository path.")] = Path("."),
    db: Annotated[
        Path | None, typer.Option("--db", help="Override the SQLite database path.")
    ] = None,
) -> None:
    """Change impact: who calls this symbol, and what it touches (Phase 22)."""
    settings = _settings(path, db)
    if not settings.db_path.exists():
        console.print(f"[yellow]No index found at[/yellow] {settings.db_path}")
        raise typer.Exit(code=1)
    with Database(settings.db_path) as store:
        conn = store.connection
        repo = RepositoryStore(conn).get_by_path(str(path.resolve()))
        if repo is None:
            console.print("[yellow]Repository not indexed at this path.[/yellow]")
            raise typer.Exit(code=1)
        symbols = SymbolStore(conn).list_for_repository(repo.id)
    report = ImpactAnalyzer(symbols).impact(symbol)
    if report.targets == 0:
        console.print(f"[dim]No symbol named[/dim] {symbol}")
        raise typer.Exit(code=1)
    console.print(
        f"[bold]Impact of changing[/bold] {symbol} "
        f"({report.targets} definition(s)) — heuristic, name-based:"
    )
    console.print(f"  Direct callers:   {len(report.direct_callers)}")
    for label in report.direct_callers[:15]:
        console.print(f"    [dim]{label}[/dim]")
    console.print(f"  Indirect callers: {len(report.indirect_callers)}")
    console.print(f"  Affected files:   {len(report.affected_files)}")
    console.print(f"  Affected modules: {', '.join(report.affected_modules[:8])}")
    if report.affected_tests:
        console.print(f"  Affected tests:   {', '.join(report.affected_tests[:8])}")


@app.command()
def intel(
    path: Annotated[Path, typer.Argument(help="Repository path.")],
    diff: Annotated[
        bool, typer.Option("--diff", help="Diff against the previously stored findings.")
    ] = False,
    origin: Annotated[
        str | None, typer.Option("--origin", help="Filter: STATIC_ANALYSIS or LLM_INFERENCE.")
    ] = None,
    db: Annotated[
        Path | None, typer.Option("--db", help="Override the SQLite database path.")
    ] = None,
) -> None:
    """Repository intelligence: smells, patterns, hotspots, domains (Phases 13/21)."""
    settings = _settings(path, db)
    if not settings.db_path.exists():
        console.print(f"[yellow]No index found at[/yellow] {settings.db_path}")
        raise typer.Exit(code=1)
    with Database(settings.db_path) as store:
        conn = store.connection
        repo = RepositoryStore(conn).get_by_path(str(path.resolve()))
        if repo is None:
            console.print("[yellow]Repository not indexed at this path.[/yellow]")
            raise typer.Exit(code=1)
        finding_store = FindingStore(conn)
        previous = {_finding_key(f) for f in finding_store.list_for_repository(repo.id)}
        report = IntelligenceEngine(conn, path.resolve()).analyze(repo.id)
        finding_store.replace_all(repo.id, report.findings)
        conn.commit()

    findings = report.findings
    if origin is not None:
        findings = [f for f in findings if f.origin == origin]

    console.print(
        f"[bold]{len(findings)} findings[/bold]  "
        + "  ".join(f"{k}:{v}" for k, v in report.by_category.items())
    )
    if diff:
        current_keys = {_finding_key(f) for f in report.findings}
        new = current_keys - previous
        resolved = previous - current_keys
        console.print(f"[green]+{len(new)} new[/green]  [red]-{len(resolved)} resolved[/red]")

    table = Table(title="Findings", header_style="bold cyan")
    table.add_column("Conf", justify="right")
    table.add_column("Origin")
    table.add_column("Category")
    table.add_column("Title")
    for finding in sorted(findings, key=lambda f: -f.confidence)[:40]:
        table.add_row(
            f"{finding.confidence:.2f}",
            "static" if finding.origin == "STATIC_ANALYSIS" else "llm",
            finding.category,
            finding.title,
        )
    console.print(table)


def _finding_key(finding: Finding) -> str:
    return f"{finding.category}|{finding.target}|{finding.title}"


@app.command()
def update(
    path: Annotated[Path, typer.Argument(help="Repository path to update.")],
    db: Annotated[
        Path | None, typer.Option("--db", help="Override the SQLite database path.")
    ] = None,
) -> None:
    """Incrementally update the index (only changed files are touched)."""
    if not path.exists():
        console.print(f"[red]Path does not exist:[/red] {path}")
        raise typer.Exit(code=2)
    settings = _settings(path, db)
    report = Indexer(settings).index(path)
    RepositoryRegistry().record(
        repo_path=path.resolve(), name=path.resolve().name, db_path=settings.db_path
    )
    console.print(
        f"[green]Updated[/green] added {report.added}  changed {report.changed}  "
        f"removed {report.removed}  unchanged {report.unchanged}  "
        f"(touched {report.touched}, symbols {report.symbols_total})"
    )
    if report.changed or report.removed:
        console.print(
            "[dim]Enrichment/embeddings for changed or removed files were "
            "invalidated (FK cascade); re-run enrich/embed to refresh.[/dim]"
        )


@app.command()
def delete(
    path: Annotated[Path, typer.Argument(help="Repository path to remove from the index.")],
    db: Annotated[
        Path | None, typer.Option("--db", help="Override the SQLite database path.")
    ] = None,
) -> None:
    """Delete a repository's knowledge base (symbols, enrichment, embeddings)."""
    settings = _settings(path, db)
    if not settings.db_path.exists():
        console.print(f"[yellow]No index found at[/yellow] {settings.db_path}")
        raise typer.Exit(code=1)
    with Database(settings.db_path) as store:
        conn = store.connection
        repo = RepositoryStore(conn).get_by_path(str(path.resolve()))
        if repo is None:
            console.print("[yellow]Repository not indexed at this path.[/yellow]")
            raise typer.Exit(code=1)
        with conn:
            conn.execute("DELETE FROM repositories WHERE id = ?", (repo.id,))
    RepositoryRegistry().remove(path.resolve())
    console.print(f"[green]Deleted[/green] repository data for {path}")


@app.command()
def config(
    path: Annotated[Path, typer.Option("--path", help="Repository path.")] = Path("."),
    db: Annotated[
        Path | None, typer.Option("--db", help="Override the SQLite database path.")
    ] = None,
) -> None:
    """Show the effective configuration (nothing is hardcoded)."""
    settings = _settings(path, db)
    llm = settings.llm
    table = Table(title="Effective configuration", header_style="bold cyan")
    table.add_column("Setting")
    table.add_column("Value")
    table.add_row("db_path", str(settings.db_path))
    table.add_row("max_file_bytes", str(settings.scan.max_file_bytes))
    table.add_row("llm.base_url", llm.base_url)
    table.add_row("llm.model", llm.model)
    table.add_row("llm.temperature", str(llm.temperature))
    table.add_row("llm.max_tokens", str(llm.max_tokens))
    table.add_row("llm.max_retries", str(llm.max_retries))
    table.add_row("llm.batch_size", str(llm.batch_size))
    table.add_row("llm.max_concurrency", str(llm.max_concurrency))
    console.print(table)


@app.command()
def serve(
    host: Annotated[str, typer.Option("--host", help="Bind host.")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", help="Bind port.")] = 8000,
) -> None:
    """Run the HTTP API (requires `uvicorn`)."""
    try:
        import uvicorn
    except ImportError:
        console.print(
            "[yellow]uvicorn is not installed.[/yellow] Install it, or run:\n"
            "  uv run uvicorn code_intel.api.app:app"
        )
        raise typer.Exit(code=1) from None
    uvicorn.run("code_intel.api.app:app", host=host, port=port)


@app.command()
def ui(
    host: Annotated[str, typer.Option("--host", help="Bind host.")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", help="Bind port.")] = 8000,
    open_browser: Annotated[
        bool, typer.Option("--open/--no-open", help="Open the browser on launch.")
    ] = True,
) -> None:
    """Serve the API + browser UI, opening it in a browser (requires `uvicorn`)."""
    try:
        import uvicorn
    except ImportError:
        console.print(
            "[yellow]uvicorn is not installed.[/yellow] Install the serve extra:\n"
            "  uv add uvicorn   # or: uv sync --extra serve"
        )
        raise typer.Exit(code=1) from None
    url = f"http://{host}:{port}/"
    if open_browser:
        import threading
        import webbrowser

        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    console.print(f"[green]Code Intelligence UI[/green] → {url}")
    uvicorn.run("code_intel.api.app:app", host=host, port=port)


@app.command()
def version() -> None:
    """Print the platform version."""
    console.print(__version__)


def _stats_dict(report: DependencyReport) -> dict[str, object]:
    return {
        "files": report.files,
        "symbols": report.symbols,
        "languages": report.languages,
        "call_edges": report.call_edges,
        "import_edges": report.import_edges,
        "duplicate_implementations": [
            {"count": g.count, "names": g.names, "paths": g.paths}
            for g in report.duplicate_implementations
        ],
        "circular_dependencies": report.circular_dependencies,
        "dead_code_candidates": report.dead_code_candidates,
        "orphan_modules": report.orphan_modules,
        "entry_points": report.entry_points,
        "shared_utilities": report.shared_utilities,
        "most_depended_modules": report.most_depended_modules,
    }


def _render_stats(report: DependencyReport) -> None:
    overview = Table(title="Repository Stats", header_style="bold cyan")
    overview.add_column("Metric")
    overview.add_column("Value", justify="right")
    overview.add_row("Files", str(report.files))
    overview.add_row("Symbols", str(report.symbols))
    overview.add_row("Languages", ", ".join(f"{k}:{v}" for k, v in report.languages.items()))
    overview.add_row("Call edges", str(report.call_edges))
    overview.add_row("Import edges", str(report.import_edges))
    overview.add_row("Circular dependencies", str(len(report.circular_dependencies)))
    overview.add_row("Duplicate impl. groups", str(len(report.duplicate_implementations)))
    overview.add_row("Dead-code candidates", str(len(report.dead_code_candidates)))
    overview.add_row("Orphan modules", str(len(report.orphan_modules)))
    overview.add_row("Entry points", str(len(report.entry_points)))
    console.print(overview)

    if report.shared_utilities:
        console.print("[bold]Most-called symbols (shared utilities, heuristic):[/bold]")
        for name, count in report.shared_utilities:
            console.print(f"  {count:>4}×  {name}")
    if report.most_depended_modules:
        console.print("[bold]Most-imported modules:[/bold]")
        for module_path, count in report.most_depended_modules:
            console.print(f"  {count:>4}×  {module_path}")
    if report.circular_dependencies:
        console.print("[bold red]Circular dependencies:[/bold red]")
        for cycle in report.circular_dependencies:
            console.print("  " + " → ".join(cycle))
    if report.duplicate_implementations:
        console.print("[bold]Duplicate implementations (identical code):[/bold]")
        for group in report.duplicate_implementations:
            console.print(f"  {group.count}× {', '.join(group.names)}")


def _render_symbols_for_file(symbol_store: SymbolStore, repo_id: str, file: str) -> None:
    rows = symbol_store.list_for_path(repo_id, file)
    if not rows:
        console.print(f"[dim]No symbols recorded for[/dim] {file}")
        return
    by_id = {s.id: s.name for s in rows}
    table = Table(title=f"Symbols in {file}", header_style="bold cyan")
    table.add_column("Lines", justify="right")
    table.add_column("Type")
    table.add_column("Visibility")
    table.add_column("Name")
    table.add_column("Parent")
    for s in rows:
        parent = by_id.get(s.parent_id, "") if s.parent_id else ""
        table.add_row(f"{s.start_line}-{s.end_line}", s.type, s.visibility, s.name, parent)
    console.print(table)


def _render_symbol_breakdown(conn: sqlite3.Connection, repo_id: str) -> None:
    rows = conn.execute(
        "SELECT type, COUNT(*) AS n FROM symbols WHERE repository_id = ? "
        "GROUP BY type ORDER BY n DESC",
        (repo_id,),
    ).fetchall()
    if not rows:
        console.print("[dim]No symbols recorded. Run `code-intel index` first.[/dim]")
        return
    table = Table(title="Symbols by type", header_style="bold cyan")
    table.add_column("Type")
    table.add_column("Count", justify="right")
    for row in rows:
        table.add_row(row["type"], str(row["n"]))
    console.print(table)


def _report_dict(report: IndexReport, db_path: Path) -> dict[str, object]:
    return {
        "repository_id": report.repository_id,
        "repository_path": report.repository_path,
        "db_path": str(db_path),
        "added": report.added,
        "changed": report.changed,
        "unchanged": report.unchanged,
        "removed": report.removed,
        "total_indexed": report.total_indexed,
        "touched": report.touched,
        "symbols_parsed": report.symbols_parsed,
        "symbols_total": report.symbols_total,
        "skipped": {
            "ignored": report.counters.skipped_ignored,
            "unknown_language": report.counters.skipped_unknown_language,
            "binary": report.counters.skipped_binary,
            "too_large": report.counters.skipped_too_large,
        },
        "duration_s": round(report.duration_s, 4),
    }


def _render_report(report: IndexReport, db_path: Path) -> None:
    table = Table(title="Index Report", show_header=True, header_style="bold cyan")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Repository", report.repository_path)
    table.add_row("Database", str(db_path))
    table.add_row("Added", str(report.added))
    table.add_row("Changed", str(report.changed))
    table.add_row("Unchanged", str(report.unchanged))
    table.add_row("Removed", str(report.removed))
    table.add_row("Total indexed", str(report.total_indexed))
    table.add_row("Symbols parsed (this run)", str(report.symbols_parsed))
    table.add_row("Symbols total", str(report.symbols_total))
    table.add_row("Skipped (ignored)", str(report.counters.skipped_ignored))
    table.add_row("Skipped (unknown lang)", str(report.counters.skipped_unknown_language))
    table.add_row("Skipped (binary)", str(report.counters.skipped_binary))
    table.add_row("Skipped (too large)", str(report.counters.skipped_too_large))
    table.add_row("Duration (s)", f"{report.duration_s:.3f}")
    console.print(table)


if __name__ == "__main__":
    app()
