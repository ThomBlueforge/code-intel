"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  ApiError,
  type FileInfo,
  type FileSymbol,
  getFileSymbols,
  getFiles,
} from "@/lib/api";
import { Badge, EmptyState, Panel, Spinner } from "./ui";

type OpenSource = (file: string, start?: number, end?: number) => void;

interface Props {
  repoPath: string;
  onOpenSource: OpenSource;
}

export function Symbols({ repoPath, onOpenSource }: Props) {
  const [files, setFiles] = useState<FileInfo[]>([]);
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [symbols, setSymbols] = useState<FileSymbol[] | null>(null);
  const [loadingFiles, setLoadingFiles] = useState(true);
  const [loadingSyms, setLoadingSyms] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoadingFiles(true);
    setError(null);
    setSelected(null);
    setSymbols(null);
    getFiles(repoPath)
      .then((r) => {
        if (!cancelled) setFiles(r.files);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : String(err));
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingFiles(false);
      });
    return () => {
      cancelled = true;
    };
  }, [repoPath]);

  const openFile = useCallback(
    async (file: string) => {
      setSelected(file);
      setLoadingSyms(true);
      setSymbols(null);
      try {
        setSymbols((await getFileSymbols(repoPath, file)).symbols);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : String(err));
      } finally {
        setLoadingSyms(false);
      }
    },
    [repoPath],
  );

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return q ? files.filter((f) => f.path.toLowerCase().includes(q)) : files;
  }, [files, filter]);

  return (
    <Panel eyebrow="Deterministic symbols" title="Symbols">
      {error ? <div className="notice notice-danger">{error}</div> : null}
      <div className="split">
        <div className="split-side">
          <input
            className="filter-input"
            placeholder="Filter files…"
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
          />
          {loadingFiles ? (
            <div className="loading-block">
              <Spinner />
            </div>
          ) : (
            <ul className="file-list">
              {filtered.map((f) => (
                <li key={f.path}>
                  <button
                    className={`file-row${selected === f.path ? " is-active" : ""}`}
                    onClick={() => openFile(f.path)}
                  >
                    <span className="file-path mono">{f.path}</span>
                    <span className="file-lang mono">{f.language}</span>
                  </button>
                </li>
              ))}
              {filtered.length === 0 ? <li className="muted">No files.</li> : null}
            </ul>
          )}
        </div>
        <div className="split-main">
          {!selected ? (
            <EmptyState title="Select a file">
              Choose a file to list its symbols.
            </EmptyState>
          ) : loadingSyms ? (
            <div className="loading-block">
              <Spinner label="Loading symbols…" />
            </div>
          ) : !symbols || symbols.length === 0 ? (
            <EmptyState title="No symbols in this file" />
          ) : (
            <ul className="symbol-list">
              {symbols.map((s) => (
                <li key={s.id}>
                  <button
                    className="symbol-row"
                    onClick={() => onOpenSource(selected, s.start_line, s.end_line)}
                  >
                    <span className="symbol-kind mono">{s.type}</span>
                    <span className="symbol-name">
                      {s.name}
                      {s.parent ? (
                        <span className="symbol-parent mono"> · {s.parent}</span>
                      ) : null}
                    </span>
                    <span className="symbol-vis">
                      {s.visibility !== "public" ? (
                        <Badge>{s.visibility}</Badge>
                      ) : null}
                    </span>
                    <span className="symbol-lines mono">
                      {s.start_line}–{s.end_line}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </Panel>
  );
}
