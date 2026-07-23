"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { AiLayers } from "@/components/AiLayers";
import { Ask } from "@/components/Ask";
import { Explain } from "@/components/Explain";
import { Graph } from "@/components/Graph";
import { Impact } from "@/components/Impact";
import { Intelligence } from "@/components/Intelligence";
import { Overview } from "@/components/Overview";
import { RepoDashboard } from "@/components/RepoDashboard";
import { Search } from "@/components/Search";
import { SourceViewer } from "@/components/SourceViewer";
import { Symbols } from "@/components/Symbols";
import { Button, EmptyState, Spinner } from "@/components/ui";
import { ApiError, type RepoEntry, getRepos } from "@/lib/api";

interface SourceTarget {
  file: string;
  start?: number;
  end?: number;
}

type ViewId =
  | "repos"
  | "overview"
  | "search"
  | "symbols"
  | "graph"
  | "ask"
  | "explain"
  | "impact"
  | "intel"
  | "ai";

interface NavItem {
  id: ViewId;
  label: string;
  glyph: string;
  enabled: boolean;
  needsRepo?: boolean;
}

const NAV: NavItem[] = [
  { id: "repos", label: "Repositories", glyph: "◈", enabled: true },
  { id: "overview", label: "Overview", glyph: "▤", enabled: true, needsRepo: true },
  { id: "search", label: "Search", glyph: "⌕", enabled: true, needsRepo: true },
  { id: "symbols", label: "Symbols", glyph: "ƒ", enabled: true, needsRepo: true },
  { id: "graph", label: "Graph", glyph: "⌗", enabled: true, needsRepo: true },
  { id: "ask", label: "Ask", glyph: "?", enabled: true, needsRepo: true },
  { id: "explain", label: "Explain", glyph: "≡", enabled: true, needsRepo: true },
  { id: "impact", label: "Impact", glyph: "↯", enabled: true, needsRepo: true },
  { id: "intel", label: "Intelligence", glyph: "✦", enabled: true, needsRepo: true },
  { id: "ai", label: "AI layers", glyph: "⚙", enabled: true, needsRepo: true },
];

type Theme = "system" | "light" | "dark";

function applyTheme(theme: Theme): void {
  const el = document.documentElement;
  if (theme === "system") {
    delete el.dataset.theme;
    localStorage.removeItem("ci-theme");
  } else {
    el.dataset.theme = theme;
    localStorage.setItem("ci-theme", theme);
  }
}

export default function Page() {
  const [repos, setRepos] = useState<RepoEntry[]>([]);
  const [activePath, setActivePath] = useState<string | null>(null);
  const [view, setView] = useState<ViewId>("repos");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [theme, setTheme] = useState<Theme>("system");
  const [sourceTarget, setSourceTarget] = useState<SourceTarget | null>(null);

  const reload = useCallback(async () => {
    try {
      const data = await getRepos();
      setRepos(data.repositories);
      setActivePath((current) => {
        if (current && data.repositories.some((r) => r.path === current)) return current;
        return data.repositories[0]?.path ?? null;
      });
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const stored = localStorage.getItem("ci-theme");
    if (stored === "light" || stored === "dark") setTheme(stored);
    void reload();
  }, [reload]);

  const cycleTheme = useCallback(() => {
    setTheme((current) => {
      const next: Theme =
        current === "system" ? "light" : current === "light" ? "dark" : "system";
      applyTheme(next);
      return next;
    });
  }, []);

  const openOverview = useCallback((path: string) => {
    setActivePath(path);
    setView("overview");
  }, []);

  const openSource = useCallback((file: string, start?: number, end?: number) => {
    setSourceTarget({ file, start, end });
  }, []);

  const activeRepo = useMemo(
    () => repos.find((r) => r.path === activePath) ?? null,
    [repos, activePath],
  );

  const themeLabel = theme === "system" ? "Auto" : theme === "light" ? "Light" : "Dark";

  return (
    <div className="app">
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            ◇
          </span>
          <span className="brand-text">
            code<span className="brand-dim">·</span>intel
          </span>
        </div>
        <nav className="nav" aria-label="Primary">
          {NAV.map((item) => {
            const disabled = !item.enabled || (item.needsRepo && !activePath);
            const isActive = view === item.id;
            return (
              <button
                key={item.id}
                className={`nav-item${isActive ? " is-active" : ""}`}
                disabled={disabled}
                onClick={() => setView(item.id)}
                title={
                  !item.enabled
                    ? "Coming soon"
                    : item.needsRepo && !activePath
                      ? "Select a repository first"
                      : undefined
                }
              >
                <span className="nav-glyph" aria-hidden="true">
                  {item.glyph}
                </span>
                <span className="nav-label">{item.label}</span>
                {!item.enabled ? <span className="nav-soon">soon</span> : null}
              </button>
            );
          })}
        </nav>
        <div className="sidebar-foot">
          <span className="foot-note">deterministic facts · optional AI</span>
        </div>
      </aside>

      <div className="content">
        <header className="topbar">
          <div className="topbar-left">
            {repos.length > 0 ? (
              <label className="repo-switch">
                <span className="repo-switch-label">Repository</span>
                <select
                  value={activePath ?? ""}
                  onChange={(event) => setActivePath(event.target.value || null)}
                >
                  {repos.map((repo) => (
                    <option key={repo.path} value={repo.path}>
                      {repo.name}
                    </option>
                  ))}
                </select>
              </label>
            ) : (
              <span className="topbar-hint">No repository selected</span>
            )}
          </div>
          <div className="topbar-right">
            <Button variant="ghost" onClick={cycleTheme} title="Toggle theme">
              {themeLabel}
            </Button>
          </div>
        </header>

        <main className="main" id="main" tabIndex={-1} key={view}>
          <div className="main-inner enter">
            {loading ? (
              <div className="loading-block">
                <Spinner label="Loading…" />
              </div>
            ) : error ? (
              <div className="notice notice-danger">{error}</div>
            ) : view === "repos" ? (
              <RepoDashboard
                repos={repos}
                activePath={activePath}
                onReload={reload}
                onSelect={setActivePath}
                onOpenOverview={openOverview}
              />
            ) : view === "overview" && activeRepo ? (
              <Overview repoPath={activeRepo.path} />
            ) : view === "search" && activeRepo ? (
              <Search repoPath={activeRepo.path} onOpenSource={openSource} />
            ) : view === "symbols" && activeRepo ? (
              <Symbols repoPath={activeRepo.path} onOpenSource={openSource} />
            ) : view === "graph" && activeRepo ? (
              <Graph repoPath={activeRepo.path} />
            ) : view === "ask" && activeRepo ? (
              <Ask repoPath={activeRepo.path} onOpenSource={openSource} />
            ) : view === "explain" && activeRepo ? (
              <Explain repoPath={activeRepo.path} />
            ) : view === "impact" && activeRepo ? (
              <Impact repoPath={activeRepo.path} onOpenSource={openSource} />
            ) : view === "intel" && activeRepo ? (
              <Intelligence repoPath={activeRepo.path} />
            ) : view === "ai" && activeRepo ? (
              <AiLayers repoPath={activeRepo.path} />
            ) : (
              <EmptyState
                title="Select a repository"
                action={
                  <Button variant="accent" onClick={() => setView("repos")}>
                    Go to repositories
                  </Button>
                }
              >
                Choose an indexed repository to see its overview.
              </EmptyState>
            )}
          </div>
        </main>
      </div>

      {sourceTarget && activeRepo ? (
        <SourceViewer
          repoPath={activeRepo.path}
          file={sourceTarget.file}
          focusStart={sourceTarget.start}
          focusEnd={sourceTarget.end}
          onClose={() => setSourceTarget(null)}
        />
      ) : null}
    </div>
  );
}
