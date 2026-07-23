"use client";

import { type FormEvent, useState } from "react";

import { ApiError, type Explanation, explain } from "@/lib/api";
import { Button, Panel, Spinner } from "./ui";

interface Props {
  repoPath: string;
}

export function Explain({ repoPath }: Props) {
  const [target, setTarget] = useState(".");
  const [data, setData] = useState<Explanation | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    const t = target.trim();
    if (!t) return;
    setLoading(true);
    setError(null);
    setData(null);
    try {
      setData(await explain(repoPath, t));
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
      <Panel
        eyebrow="Hierarchical summaries"
        title="Explain"
        actions={
          <form className="graph-form" onSubmit={onSubmit}>
            <input
              className="search-input"
              placeholder="'.', a file/dir, or a symbol"
              value={target}
              onChange={(event) => setTarget(event.target.value)}
            />
            <Button variant="accent" type="submit" disabled={loading}>
              {loading ? <Spinner /> : "Explain"}
            </Button>
          </form>
        }
      >
        {error ? <div className="notice notice-danger">{error}</div> : null}
        {!data ? (
          loading ? (
            <div className="loading-block">
              <Spinner label="Summarising…" />
            </div>
          ) : (
            <p className="muted">
              Explain the whole repository (<span className="mono">.</span>), a file
              or directory, or a symbol by name.
            </p>
          )
        ) : (
          <div>
            <div className="explain-head">
              <span className="badge">{data.scope}</span>
              <span className="mono">{data.target}</span>
            </div>
            <p className="answer-text">{data.summary}</p>
            {data.details.length ? (
              <ul className="plain-list">
                {data.details.map((d, i) => (
                  <li key={`${d}-${i}`} className="mono">
                    {d}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        )}
      </Panel>
    </div>
  );
}
