"use client";

import { useEffect, useMemo, useState } from "react";

import { ApiError, type Intel, getIntel } from "@/lib/api";
import { OriginBadge, Panel, Spinner, Stat } from "./ui";

type OriginFilter = "all" | "STATIC_ANALYSIS" | "LLM_INFERENCE";

interface Props {
  repoPath: string;
}

export function Intelligence({ repoPath }: Props) {
  const [data, setData] = useState<Intel | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [origin, setOrigin] = useState<OriginFilter>("all");
  const [category, setCategory] = useState("all");
  const [minConf, setMinConf] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);
    getIntel(repoPath, { diff: true })
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : String(err));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [repoPath]);

  const categories = useMemo(
    () => (data ? Object.keys(data.by_category).sort() : []),
    [data],
  );

  const filtered = useMemo(() => {
    if (!data) return [];
    return data.findings.filter(
      (f) =>
        (origin === "all" || f.origin === origin) &&
        (category === "all" || f.category === category) &&
        f.confidence >= minConf,
    );
  }, [data, origin, category, minConf]);

  if (loading) {
    return (
      <div className="loading-block">
        <Spinner label="Running intelligence…" />
      </div>
    );
  }
  if (error) return <div className="notice notice-danger">{error}</div>;
  if (!data) return null;

  return (
    <div className="stack-lg">
      <div className="stat-grid">
        <Stat label="Findings" value={data.count} />
        {data.diff ? <Stat tone="accent" label="New" value={data.diff.new} /> : null}
        {data.diff ? (
          <Stat label="Resolved" value={data.diff.resolved} />
        ) : null}
        <Stat tone="static" label="Categories" value={categories.length} />
      </div>

      <Panel
        eyebrow="Repository intelligence"
        title="Findings"
        actions={
          <div className="filters">
            <select
              value={origin}
              onChange={(event) => setOrigin(event.target.value as OriginFilter)}
              aria-label="Filter by origin"
            >
              <option value="all">all origins</option>
              <option value="STATIC_ANALYSIS">static</option>
              <option value="LLM_INFERENCE">llm</option>
            </select>
            <select
              value={category}
              onChange={(event) => setCategory(event.target.value)}
              aria-label="Filter by category"
            >
              <option value="all">all categories</option>
              {categories.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
            <label className="conf-filter">
              ≥ {minConf.toFixed(2)}
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={minConf}
                onChange={(event) => setMinConf(Number(event.target.value))}
                aria-label="Minimum confidence"
              />
            </label>
          </div>
        }
      >
        {filtered.length === 0 ? (
          <p className="muted">No findings match the filters.</p>
        ) : (
          <ul className="finding-full-list">
            {filtered.map((f) => (
              <li key={f.id} className="finding-full">
                <div className="finding-full-head">
                  <OriginBadge origin={f.origin} />
                  <span className="cat-tag mono">{f.category}</span>
                  <span className="finding-full-title">{f.title}</span>
                  <span className="finding-conf mono">
                    {f.confidence.toFixed(2)}
                  </span>
                </div>
                {f.detail ? <p className="finding-detail">{f.detail}</p> : null}
                {f.target ? (
                  <div className="finding-target mono">{f.target}</div>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
