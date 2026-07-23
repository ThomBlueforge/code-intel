"use client";

import { type FormEvent, useState } from "react";

import {
  ApiError,
  type KeywordMatch,
  type RetrieveResult,
  type SymbolHit,
  retrieve,
  searchKeyword,
  searchSymbol,
} from "@/lib/api";
import { Badge, Button, EmptyState, Panel, Spinner } from "./ui";

type Mode = "retrieve" | "symbol" | "keyword";
type OpenSource = (file: string, start?: number, end?: number) => void;

interface Props {
  repoPath: string;
  onOpenSource: OpenSource;
}

const MODES: { id: Mode; label: string; hint: string }[] = [
  { id: "retrieve", label: "Hybrid", hint: "semantic + structural" },
  { id: "symbol", label: "Symbol", hint: "by name" },
  { id: "keyword", label: "Keyword", hint: "text / regex" },
];

function placeholder(mode: Mode): string {
  if (mode === "retrieve") return "Describe what you're looking for…";
  if (mode === "symbol") return "Symbol name (exact, prefix, or fuzzy)";
  return "Text or regex to find in files";
}

export function Search({ repoPath, onOpenSource }: Props) {
  const [mode, setMode] = useState<Mode>("retrieve");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retrieveRes, setRetrieveRes] = useState<RetrieveResult[] | null>(null);
  const [symbolRes, setSymbolRes] = useState<SymbolHit[] | null>(null);
  const [keywordRes, setKeywordRes] = useState<KeywordMatch[] | null>(null);
  const [backend, setBackend] = useState<string | null>(null);

  const reset = () => {
    setRetrieveRes(null);
    setSymbolRes(null);
    setKeywordRes(null);
    setBackend(null);
  };

  const run = async () => {
    const q = query.trim();
    if (!q) return;
    setLoading(true);
    setError(null);
    reset();
    try {
      if (mode === "retrieve") {
        setRetrieveRes((await retrieve({ path: repoPath, query: q })).results);
      } else if (mode === "symbol") {
        setSymbolRes((await searchSymbol(repoPath, q)).results);
      } else {
        const res = await searchKeyword({ path: repoPath, keyword: q });
        setKeywordRes(res.matches);
        setBackend(res.backend);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void run();
  };

  return (
    <div className="stack-lg">
      <Panel eyebrow="Retrieval" title="Search">
        <div className="segmented" role="tablist">
          {MODES.map((m) => (
            <button
              key={m.id}
              role="tab"
              aria-selected={mode === m.id}
              className={`seg${mode === m.id ? " is-active" : ""}`}
              onClick={() => {
                setMode(m.id);
                reset();
              }}
            >
              {m.label}
              <span className="seg-hint">{m.hint}</span>
            </button>
          ))}
        </div>
        <form className="search-form" onSubmit={onSubmit}>
          <input
            className="search-input"
            value={query}
            placeholder={placeholder(mode)}
            onChange={(event) => setQuery(event.target.value)}
            autoFocus
          />
          <Button variant="accent" type="submit" disabled={loading}>
            {loading ? <Spinner /> : "Search"}
          </Button>
        </form>
        {error ? <div className="notice notice-danger">{error}</div> : null}
      </Panel>

      {loading ? null : (
        <>
          {retrieveRes ? (
            <RetrieveResults results={retrieveRes} onOpen={onOpenSource} />
          ) : null}
          {symbolRes ? (
            <SymbolResults results={symbolRes} onOpen={onOpenSource} />
          ) : null}
          {keywordRes ? (
            <KeywordResults
              results={keywordRes}
              backend={backend}
              onOpen={onOpenSource}
            />
          ) : null}
        </>
      )}
    </div>
  );
}

function RetrieveResults({
  results,
  onOpen,
}: {
  results: RetrieveResult[];
  onOpen: OpenSource;
}) {
  if (results.length === 0) {
    return (
      <Panel title="Hybrid results">
        <EmptyState title="No results" />
      </Panel>
    );
  }
  return (
    <Panel eyebrow={`${results.length} results`} title="Hybrid results">
      <ul className="result-list">
        {results.map((r, i) => (
          <li key={`${r.path}:${r.start_line}:${i}`}>
            <button className="result-row" onClick={() => onOpen(r.path, r.start_line)}>
              <span className="result-score mono">{r.score.toFixed(3)}</span>
              <span className="result-main">
                <span className="result-name">
                  {r.name} <span className="result-kind mono">{r.type}</span>
                </span>
                <span className="result-loc mono">
                  {r.path}:{r.start_line}
                </span>
              </span>
              <span className="result-sources">
                {r.sources.map((s) => (
                  <span key={s} className="src-chip mono">
                    {s}
                  </span>
                ))}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function SymbolResults({
  results,
  onOpen,
}: {
  results: SymbolHit[];
  onOpen: OpenSource;
}) {
  if (results.length === 0) {
    return (
      <Panel title="Symbol results">
        <EmptyState title="No symbols" />
      </Panel>
    );
  }
  return (
    <Panel eyebrow={`${results.length} results`} title="Symbol results">
      <ul className="result-list">
        {results.map((r, i) => (
          <li key={`${r.path}:${r.line}:${i}`}>
            <button className="result-row" onClick={() => onOpen(r.path, r.line)}>
              <span className="result-score mono">{r.score.toFixed(2)}</span>
              <span className="result-main">
                <span className="result-name">
                  {r.name} <span className="result-kind mono">{r.type}</span>
                </span>
                <span className="result-loc mono">
                  {r.path}:{r.line}
                </span>
              </span>
              <Badge>{r.match}</Badge>
            </button>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function KeywordResults({
  results,
  backend,
  onOpen,
}: {
  results: KeywordMatch[];
  backend: string | null;
  onOpen: OpenSource;
}) {
  if (results.length === 0) {
    return (
      <Panel title="Keyword matches">
        <EmptyState title="No matches" />
      </Panel>
    );
  }
  return (
    <Panel
      eyebrow={backend ? `${results.length} · ${backend}` : `${results.length}`}
      title="Keyword matches"
    >
      <ul className="result-list">
        {results.map((m, i) => (
          <li key={`${m.path}:${m.line}:${i}`}>
            <button
              className="result-row is-code"
              onClick={() => onOpen(m.path, m.line)}
            >
              <span className="result-loc mono">
                {m.path}:{m.line}
              </span>
              <code className="result-code mono">{m.text}</code>
            </button>
          </li>
        ))}
      </ul>
    </Panel>
  );
}
