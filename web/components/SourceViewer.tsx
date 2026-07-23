"use client";

import { useEffect, useRef, useState } from "react";

import { ApiError, type FileSource, getFileSource } from "@/lib/api";
import { Button, Spinner } from "./ui";

interface Props {
  repoPath: string;
  file: string;
  focusStart?: number;
  focusEnd?: number;
  onClose: () => void;
}

export function SourceViewer({
  repoPath,
  file,
  focusStart,
  focusEnd,
  onClose,
}: Props) {
  const [source, setSource] = useState<FileSource | null>(null);
  const [error, setError] = useState<string | null>(null);
  const focusRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    setSource(null);
    setError(null);
    getFileSource(repoPath, file)
      .then((s) => {
        if (!cancelled) setSource(s);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : String(err));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [repoPath, file]);

  useEffect(() => {
    if (source && focusRef.current) {
      focusRef.current.scrollIntoView({ block: "center" });
    }
  }, [source]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const start = focusStart ?? 0;
  const end = focusEnd ?? focusStart ?? -1;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="source-modal"
        role="dialog"
        aria-modal="true"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="modal-head">
          <div className="modal-path mono">
            {file}
            {source ? ` · ${source.total_lines} lines` : ""}
          </div>
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
        </header>
        <div className="source-body">
          {error ? (
            <div className="notice notice-danger">{error}</div>
          ) : !source ? (
            <div className="loading-block">
              <Spinner label="Loading source…" />
            </div>
          ) : (
            <div className="code">
              {source.lines.map((line, i) => {
                const n = source.start + i;
                const focused = n >= start && n <= end;
                return (
                  <div
                    key={n}
                    ref={focused && n === start ? focusRef : undefined}
                    className={`src-line${focused ? " is-focus" : ""}`}
                  >
                    <span className="src-num mono">{n}</span>
                    <span className="src-code mono">{line || " "}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
