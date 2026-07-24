"use client";

import { useEffect, useState } from "react";

import {
  ApiError,
  getIntel,
  getStats,
  getUnderstanding,
  type Intel,
  type RepoUnderstanding,
  type Stats,
} from "@/lib/api";
import { Badge, OriginBadge, Panel, Spinner, Stat } from "./ui";

interface Props {
  repoPath: string;
}

function ListOrEmpty({ items, limit = 12 }: { items: string[]; limit?: number }) {
  if (items.length === 0) return <p className="muted">None.</p>;
  return (
    <ul className="plain-list">
      {items.slice(0, limit).map((item) => (
        <li key={item} className="mono">
          {item}
        </li>
      ))}
      {items.length > limit ? (
        <li className="muted">+{items.length - limit} more</li>
      ) : null}
    </ul>
  );
}

export function Overview({ repoPath }: Props) {
  const [stats, setStats] = useState<Stats | null>(null);
  const [intel, setIntel] = useState<Intel | null>(null);
  const [overview, setOverview] = useState<RepoUnderstanding | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setStats(null);
    setIntel(null);
    setOverview(null);
    Promise.all([
      getStats(repoPath),
      getIntel(repoPath),
      getUnderstanding(repoPath).catch(() => null), // optional layer
    ])
      .then(([s, i, u]) => {
        if (!cancelled) {
          setStats(s);
          setIntel(i);
          setOverview(u?.repo ?? null);
        }
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

  if (loading) {
    return (
      <div className="loading-block">
        <Spinner label="Analysing repository…" />
      </div>
    );
  }
  if (error) return <div className="notice notice-danger">{error}</div>;
  if (!stats) return null;

  const languages = Object.entries(stats.languages).sort((a, b) => b[1] - a[1]);
  const maxLang = languages.length ? languages[0][1] : 1;
  const categories = intel
    ? Object.entries(intel.by_category).sort((a, b) => b[1] - a[1])
    : [];

  return (
    <div className="stack-lg">
      {overview ? (
        <Panel
          eyebrow="Codebase comprehension"
          title="What this project is"
          actions={
            <Badge tone={overview.source === "llm" ? "ok" : "neutral"}>
              {overview.source === "llm" ? "AI synthesis" : "static"}
            </Badge>
          }
        >
          <p className="overview-summary">{overview.summary}</p>
          {overview.architecture.length ? (
            <ul className="overview-arch">
              {overview.architecture.map((bullet, i) => (
                <li key={`${bullet}-${i}`}>{bullet}</li>
              ))}
            </ul>
          ) : null}
          {overview.entry_points.length ? (
            <p className="overview-entry">
              <span className="fileu-collab-label">Entry points:</span>{" "}
              {overview.entry_points.slice(0, 6).map((e) => (
                <span key={e} className="mono fileu-collab-item">
                  {e}
                </span>
              ))}
            </p>
          ) : null}
        </Panel>
      ) : null}

      <div className="stat-grid">
        <Stat tone="accent" label="Files" value={stats.files} />
        <Stat label="Symbols" value={stats.symbols} />
        <Stat
          tone="static"
          label="Call edges"
          value={stats.call_edges}
          hint="static analysis"
        />
        <Stat
          tone="static"
          label="Import edges"
          value={stats.import_edges}
          hint="static analysis"
        />
        <Stat
          tone={stats.circular_dependencies.length ? "warn" : "default"}
          label="Cycles"
          value={stats.circular_dependencies.length}
        />
        <Stat label="Findings" value={intel ? intel.count : "—"} />
      </div>

      <div className="two-col">
        <Panel eyebrow="Composition" title="Languages">
          {languages.length === 0 ? (
            <p className="muted">No languages detected.</p>
          ) : (
            <ul className="bars">
              {languages.map(([lang, n]) => (
                <li key={lang} className="bar-row">
                  <span className="bar-label mono">{lang}</span>
                  <span className="bar-track">
                    <span
                      className="bar-fill"
                      style={{ width: `${Math.max(4, (n / maxLang) * 100)}%` }}
                    />
                  </span>
                  <span className="bar-value mono">{n}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel
          eyebrow="Repository intelligence"
          title="Findings"
          actions={<span className="provenance-note">origin shown per finding</span>}
        >
          {!intel || intel.count === 0 ? (
            <p className="muted">No findings.</p>
          ) : (
            <>
              <ul className="cat-list">
                {categories.map(([cat, n]) => (
                  <li key={cat} className="cat-row">
                    <span className="cat-name">{cat}</span>
                    <span className="cat-count mono">{n}</span>
                  </li>
                ))}
              </ul>
              <ul className="finding-list">
                {intel.findings.slice(0, 8).map((finding) => (
                  <li key={finding.id} className="finding-row">
                    <OriginBadge origin={finding.origin} />
                    <span className="finding-title">{finding.title}</span>
                    <span className="finding-conf mono">
                      {finding.confidence.toFixed(2)}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Panel>
      </div>

      {stats.circular_dependencies.length > 0 ? (
        <Panel eyebrow="Risk" title="Circular dependencies">
          <ul className="cycle-list">
            {stats.circular_dependencies.slice(0, 8).map((cycle) => (
              <li key={cycle.join(">")} className="cycle-row mono">
                {cycle.join(" → ")}
              </li>
            ))}
          </ul>
        </Panel>
      ) : null}

      <div className="two-col">
        <Panel eyebrow="Heuristic" title="Dead-code candidates">
          <ListOrEmpty items={stats.dead_code_candidates} />
        </Panel>
        <Panel eyebrow="Heuristic" title="Most-called (shared utilities)">
          {stats.shared_utilities.length === 0 ? (
            <p className="muted">None.</p>
          ) : (
            <ul className="rank-list">
              {stats.shared_utilities.map(([name, n]) => (
                <li key={name} className="rank-row">
                  <span className="mono">{name}</span>
                  <span className="rank-count mono">{n}×</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}
