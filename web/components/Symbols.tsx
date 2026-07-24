"use client";

import { useEffect, useMemo, useState } from "react";

import {
  ApiError,
  type FileUnderstanding,
  getAllSymbols,
  getUnderstanding,
  type SymbolDetail,
  type SymbolPage,
  type SymbolSort,
} from "@/lib/api";
import { Badge, Button, EmptyState, Panel, Spinner } from "./ui";

type OpenSource = (file: string, start?: number, end?: number) => void;

interface Props {
  repoPath: string;
  onOpenSource: OpenSource;
}

const SORTS: { value: SymbolSort; label: string }[] = [
  { value: "loc", label: "Lines of code" },
  { value: "name", label: "Name" },
  { value: "type", label: "Kind" },
  { value: "path", label: "Path" },
  { value: "updated", label: "Last indexed" },
];

export function Symbols({ repoPath, onOpenSource }: Props) {
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [sort, setSort] = useState<SymbolSort>("loc");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState<SymbolPage | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Debounce the search box so keystrokes don't hammer the API.
  useEffect(() => {
    const t = setTimeout(() => setDebounced(query.trim()), 250);
    return () => clearTimeout(t);
  }, [query]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getAllSymbols(repoPath, { q: debounced, sort, order, limit: 500 })
      .then((res) => {
        if (cancelled) return;
        setPage(res);
        setSelectedId((prev) =>
          prev && res.symbols.some((s) => s.id === prev)
            ? prev
            : (res.symbols[0]?.id ?? null),
        );
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [repoPath, debounced, sort, order]);

  const symbols = page?.symbols ?? [];
  const maxLoc = useMemo(
    () => symbols.reduce((m, s) => Math.max(m, s.loc), 1),
    [symbols],
  );
  const selected = symbols.find((s) => s.id === selectedId) ?? null;

  return (
    <Panel
      eyebrow="Every symbol in the index"
      title="Symbols"
      actions={
        page ? (
          <span className="sym-count mono">
            {page.returned}
            {page.total > page.returned ? ` / ${page.total}` : ""} symbols
            {page.enriched_available ? " · AI enriched" : ""}
          </span>
        ) : null
      }
    >
      <div className="sym-toolbar">
        <input
          className="sym-search"
          placeholder="Search name, kind, path, signature, decorator…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <label className="sym-sort">
          <span className="sym-sort-label">Sort</span>
          <select value={sort} onChange={(e) => setSort(e.target.value as SymbolSort)}>
            {SORTS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
        <Button
          variant="ghost"
          className="sym-order"
          onClick={() => setOrder((o) => (o === "desc" ? "asc" : "desc"))}
          title={order === "desc" ? "Descending" : "Ascending"}
        >
          {order === "desc" ? "↓ high→low" : "↑ low→high"}
        </Button>
      </div>

      {error ? <div className="notice notice-danger">{error}</div> : null}

      <div className="split sym-browser">
        <div className="split-side">
          {loading ? (
            <div className="loading-block">
              <Spinner label="Loading symbols…" />
            </div>
          ) : symbols.length === 0 ? (
            <EmptyState title="No symbols match">Try a different search.</EmptyState>
          ) : (
            <ul className="sym-list">
              {symbols.map((s) => (
                <li key={s.id}>
                  <button
                    className={`sym-row${selectedId === s.id ? " is-active" : ""}`}
                    onClick={() => setSelectedId(s.id)}
                  >
                    <span className="sym-kind mono">{s.type}</span>
                    <span className="sym-name">
                      <span className="sym-name-main">
                        {s.name}
                        {s.parent ? <span className="sym-parent mono"> · {s.parent}</span> : null}
                      </span>
                      <span className="sym-path mono">{s.path}</span>
                    </span>
                    <span className="sym-loc">
                      <span className="sym-loc-num mono">{s.loc}</span>
                      <span className="sym-bar" aria-hidden="true">
                        <span
                          className="sym-bar-fill"
                          style={{ width: `${Math.max(4, (s.loc / maxLoc) * 100)}%` }}
                        />
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="split-main">
          {selected ? (
            <SymbolDetailView
              symbol={selected}
              repoPath={repoPath}
              onOpenSource={onOpenSource}
            />
          ) : (
            <EmptyState title="Select a symbol">
              Pick a symbol to see everything the index knows about it.
            </EmptyState>
          )}
        </div>
      </div>
    </Panel>
  );
}

function SymbolDetailView({
  symbol,
  repoPath,
  onOpenSource,
}: {
  symbol: SymbolDetail;
  repoPath: string;
  onOpenSource: OpenSource;
}) {
  const meta: [string, string][] = [
    ["Kind", symbol.type],
    ["Language", symbol.language],
    ["Lines", `${symbol.start_line}–${symbol.end_line} (${symbol.loc} LOC)`],
    ["Visibility", symbol.visibility],
    ["Parent", symbol.parent ?? "—"],
    ["Path", symbol.path],
    ["Hash", symbol.hash],
    ["Symbol id", symbol.id],
    ["Indexed", symbol.updated_at],
  ];
  return (
    <div className="sym-detail">
      <header className="sym-detail-head">
        <div>
          <h3 className="sym-detail-name">{symbol.name}</h3>
          {symbol.signature ? (
            <code className="sym-signature mono">{symbol.signature}</code>
          ) : null}
        </div>
        <Button
          variant="accent"
          onClick={() => onOpenSource(symbol.path, symbol.start_line, symbol.end_line)}
        >
          Open in source
        </Button>
      </header>

      {symbol.decorators.length ? (
        <div className="sym-decorators">
          {symbol.decorators.map((d) => (
            <span key={d} className="badge badge-static mono">
              @{d}
            </span>
          ))}
        </div>
      ) : null}

      <dl className="sym-meta">
        {meta.map(([k, v]) => (
          <div className="sym-meta-row" key={k}>
            <dt>{k}</dt>
            <dd className="mono">{v}</dd>
          </div>
        ))}
      </dl>

      <FileUnderstandingCard repoPath={repoPath} path={symbol.path} />

      {symbol.enriched ? (
        <EnrichedView enriched={symbol.enriched} />
      ) : (
        <p className="sym-noai muted">
          No AI enrichment for this symbol yet. Run the Enrich layer to add a summary,
          architecture layer, and quality metrics.
        </p>
      )}

      <div className="sym-code-wrap">
        <div className="eyebrow">Source</div>
        <pre className="sym-code mono">{symbol.code}</pre>
      </div>
    </div>
  );
}

function FileUnderstandingCard({
  repoPath,
  path,
}: {
  repoPath: string;
  path: string;
}) {
  const [file, setFile] = useState<FileUnderstanding | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoaded(false);
    setFile(null);
    getUnderstanding(repoPath, path)
      .then((u) => {
        if (!cancelled) setFile(u.file);
      })
      .catch(() => {
        /* understanding is optional — silent when absent */
      })
      .finally(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, [repoPath, path]);

  if (!loaded || !file) return null;

  return (
    <section className="fileu">
      <header className="fileu-head">
        <span className="eyebrow">What this file does</span>
        <span className={`badge ${file.source === "llm" ? "badge-llm" : "badge-static"}`}>
          {file.source === "llm" ? "AI" : "static"}
          {file.role ? ` · ${file.role}` : ""}
        </span>
      </header>
      <p className="fileu-summary">{file.summary}</p>
      {file.responsibilities.length ? (
        <ol className="fileu-resp">
          {file.responsibilities.map((r, i) => (
            <li key={`${r}-${i}`}>{r}</li>
          ))}
        </ol>
      ) : null}
      {file.collaborators.length ? (
        <div className="fileu-collab">
          <span className="fileu-collab-label">Collaborates with</span>
          {file.collaborators.map((c) => (
            <span key={c} className="mono fileu-collab-item">
              {c}
            </span>
          ))}
        </div>
      ) : null}
    </section>
  );
}

const METRIC_LABELS: Record<string, string> = {
  complexity: "Complexity",
  maintainability: "Maintainability",
  readability: "Readability",
  coupling: "Coupling",
  cohesion: "Cohesion",
  testability: "Testability",
  risk: "Risk",
  stability: "Stability",
  reusability: "Reusability",
  technical_debt: "Technical debt",
};

function EnrichedView({ enriched }: { enriched: NonNullable<SymbolDetail["enriched"]> }) {
  const metrics = Object.entries(enriched.quality_metrics);
  return (
    <section className="enriched">
      <header className="enriched-head">
        <span className="badge badge-llm">AI enrichment</span>
        <span className="enriched-model mono">
          {enriched.model} · confidence {Math.round(enriched.confidence * 100)}%
        </span>
      </header>

      {enriched.summary ? <p className="enriched-summary">{enriched.summary}</p> : null}

      <div className="enriched-tags">
        {enriched.architecture_layer ? (
          <Badge tone="ok">layer: {enriched.architecture_layer}</Badge>
        ) : null}
        {enriched.business_domain.map((d) => (
          <Badge key={d}>{d}</Badge>
        ))}
      </div>

      {enriched.responsibilities.length ? (
        <EnrichedList title="Responsibilities" items={enriched.responsibilities} />
      ) : null}
      {enriched.risks.length ? (
        <EnrichedList title="Risks" items={enriched.risks} tone="warn" />
      ) : null}
      {enriched.technical_debt.length ? (
        <EnrichedList title="Technical debt" items={enriched.technical_debt} tone="warn" />
      ) : null}

      <div className="enriched-metrics">
        {metrics.map(([key, value]) => (
          <div className="metric" key={key}>
            <span className="metric-label">{METRIC_LABELS[key] ?? key}</span>
            <span className="metric-track">
              <span className="metric-fill" style={{ width: `${value * 100}%` }} />
            </span>
            <span className="metric-num mono">{value.toFixed(2)}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function EnrichedList({
  title,
  items,
  tone,
}: {
  title: string;
  items: string[];
  tone?: "warn";
}) {
  return (
    <div className={`enriched-block${tone ? ` is-${tone}` : ""}`}>
      <div className="eyebrow">{title}</div>
      <ul className="enriched-listing">
        {items.map((it, i) => (
          <li key={`${title}-${i}`}>{it}</li>
        ))}
      </ul>
    </div>
  );
}
