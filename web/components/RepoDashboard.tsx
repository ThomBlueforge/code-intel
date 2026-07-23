"use client";

import { useCallback, useState } from "react";

import {
  ApiError,
  type BrowseListing,
  type JobSnapshot,
  type RepoEntry,
  browse,
  deleteRepo,
  pollJob,
  startIndex,
  startUpdate,
} from "@/lib/api";
import { Badge, Button, EmptyState, JobProgressBar, Panel, Spinner } from "./ui";

interface Props {
  repos: RepoEntry[];
  activePath: string | null;
  onReload: () => Promise<void> | void;
  onSelect: (path: string) => void;
  onOpenOverview: (path: string) => void;
}

function fmtDate(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

function message(error: unknown): string {
  return error instanceof ApiError ? error.message : String(error);
}

export function RepoDashboard({
  repos,
  activePath,
  onReload,
  onSelect,
  onOpenOverview,
}: Props) {
  const [listing, setListing] = useState<BrowseListing | null>(null);
  const [browseLoading, setBrowseLoading] = useState(false);
  const [job, setJob] = useState<JobSnapshot | null>(null);
  const [busyPath, setBusyPath] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const openBrowse = useCallback(async (dir?: string) => {
    setBrowseLoading(true);
    setError(null);
    try {
      setListing(await browse(dir));
    } catch (err) {
      setError(message(err));
    } finally {
      setBrowseLoading(false);
    }
  }, []);

  const runJob = useCallback(
    async (path: string, kind: "index" | "update") => {
      setBusyPath(path);
      setError(null);
      setJob(null);
      try {
        const initial = await (kind === "index" ? startIndex : startUpdate)(path);
        const final = await pollJob(initial.id, setJob);
        if (final.status === "error") setError(final.error ?? "Job failed");
        await onReload();
        if (final.status === "done") onSelect(path);
      } catch (err) {
        setError(message(err));
      } finally {
        setBusyPath(null);
      }
    },
    [onReload, onSelect],
  );

  const indexAndClose = useCallback(
    async (path: string) => {
      setListing(null);
      await runJob(path, "index");
    },
    [runJob],
  );

  const remove = useCallback(
    async (path: string) => {
      if (!window.confirm(`Remove ${path} from the index?`)) return;
      setError(null);
      try {
        await deleteRepo(path);
        await onReload();
      } catch (err) {
        setError(message(err));
      }
    },
    [onReload],
  );

  return (
    <div className="stack-lg">
      <Panel
        eyebrow="Deterministic index"
        title="Repositories"
        actions={
          <>
            <Button variant="ghost" onClick={() => onReload()}>
              Refresh
            </Button>
            <Button variant="accent" onClick={() => openBrowse()}>
              Add repository
            </Button>
          </>
        }
      >
        {error ? <div className="notice notice-danger">{error}</div> : null}
        {job && busyPath ? (
          <div className="active-job">
            <div className="active-job-path mono">{busyPath}</div>
            <JobProgressBar job={job} />
          </div>
        ) : null}

        {repos.length === 0 ? (
          <EmptyState
            title="No repositories indexed yet"
            action={
              <Button variant="accent" onClick={() => openBrowse()}>
                Browse for a folder
              </Button>
            }
          >
            Point the platform at a codebase to build its deterministic knowledge base.
          </EmptyState>
        ) : (
          <ul className="repo-list">
            {repos.map((repo) => {
              const isActive = repo.path === activePath;
              const isBusy = repo.path === busyPath;
              return (
                <li
                  key={repo.path}
                  className={`repo-row${isActive ? " is-active" : ""}`}
                >
                  <button
                    className="repo-main"
                    onClick={() => onOpenOverview(repo.path)}
                  >
                    <span className="repo-name">{repo.name}</span>
                    <span className="repo-path mono">{repo.path}</span>
                    <span className="repo-meta mono">
                      indexed {fmtDate(repo.last_indexed)}
                    </span>
                  </button>
                  <div className="repo-actions">
                    {repo.indexed ? (
                      <Badge tone="ok">indexed</Badge>
                    ) : (
                      <Badge tone="warn">stale</Badge>
                    )}
                    <Button
                      variant="ghost"
                      disabled={isBusy}
                      onClick={() => runJob(repo.path, "update")}
                    >
                      {isBusy ? <Spinner /> : "Update"}
                    </Button>
                    <Button
                      variant="danger"
                      disabled={isBusy}
                      onClick={() => remove(repo.path)}
                    >
                      Remove
                    </Button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Panel>

      {listing ? (
        <div className="modal-backdrop" onClick={() => setListing(null)}>
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            onClick={(event) => event.stopPropagation()}
          >
            <header className="modal-head">
              <div>
                <div className="eyebrow">Choose a folder</div>
                <div className="modal-path mono">{listing.path}</div>
              </div>
              <Button variant="ghost" onClick={() => setListing(null)}>
                Close
              </Button>
            </header>
            <div className="modal-toolbar">
              <Button
                variant="ghost"
                disabled={!listing.parent || browseLoading}
                onClick={() => listing.parent && openBrowse(listing.parent)}
              >
                ↑ Parent
              </Button>
              <Button variant="accent" onClick={() => indexAndClose(listing.path)}>
                Index this folder
              </Button>
              {browseLoading ? <Spinner label="loading" /> : null}
            </div>
            <ul className="dir-list">
              {listing.entries.length === 0 ? (
                <li className="dir-empty">No sub-folders</li>
              ) : null}
              {listing.entries.map((entry) => (
                <li key={entry.path} className="dir-row">
                  <button
                    className="dir-main"
                    onClick={() => openBrowse(entry.path)}
                  >
                    <span className="dir-name">{entry.name}</span>
                    {entry.indexed ? <Badge tone="ok">indexed</Badge> : null}
                  </button>
                  <Button variant="ghost" onClick={() => indexAndClose(entry.path)}>
                    Index
                  </Button>
                </li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}
    </div>
  );
}
