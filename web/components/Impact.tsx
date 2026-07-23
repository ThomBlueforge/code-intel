"use client";

import { type FormEvent, useState } from "react";

import { ApiError, type ImpactReport, getImpact } from "@/lib/api";
import { Button, EmptyState, Panel, Spinner, Stat } from "./ui";

type OpenSource = (file: string, start?: number, end?: number) => void;

interface Props {
  repoPath: string;
  onOpenSource: OpenSource;
}

const LOC = /^(.+?):(\d+)/;

function LocList({
  items,
  onOpen,
}: {
  items: string[];
  onOpen: (s: string) => void;
}) {
  if (!items.length) return <p className="muted">None.</p>;
  return (
    <ul className="plain-list">
      {items.slice(0, 50).map((s, i) => (
        <li key={`${s}-${i}`}>
          <button className="linkish mono" onClick={() => onOpen(s)}>
            {s}
          </button>
        </li>
      ))}
      {items.length > 50 ? (
        <li className="muted">+{items.length - 50} more</li>
      ) : null}
    </ul>
  );
}

function PlainList({ items }: { items: string[] }) {
  if (!items.length) return <p className="muted">None.</p>;
  return (
    <ul className="plain-list">
      {items.slice(0, 50).map((s, i) => (
        <li key={`${s}-${i}`} className="mono">
          {s}
        </li>
      ))}
      {items.length > 50 ? (
        <li className="muted">+{items.length - 50} more</li>
      ) : null}
    </ul>
  );
}

export function Impact({ repoPath, onOpenSource }: Props) {
  const [symbol, setSymbol] = useState("");
  const [data, setData] = useState<ImpactReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    const q = symbol.trim();
    if (!q) return;
    setLoading(true);
    setError(null);
    setData(null);
    try {
      setData(await getImpact(repoPath, q));
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

  const openLoc = (s: string) => {
    const m = LOC.exec(s);
    if (m) onOpenSource(m[1], Number(m[2]));
  };

  return (
    <div className="stack-lg">
      <Panel
        eyebrow="Change impact · heuristic, name-based"
        title="Impact"
        actions={
          <form className="graph-form" onSubmit={onSubmit}>
            <input
              className="search-input"
              placeholder="Symbol name"
              value={symbol}
              onChange={(event) => setSymbol(event.target.value)}
            />
            <Button variant="accent" type="submit" disabled={loading}>
              {loading ? <Spinner /> : "Analyse"}
            </Button>
          </form>
        }
      >
        {error ? <div className="notice notice-danger">{error}</div> : null}
        {!data ? (
          loading ? (
            <div className="loading-block">
              <Spinner label="Tracing callers…" />
            </div>
          ) : (
            <EmptyState title="Analyse change impact">
              Enter a symbol to see who calls it and what a change would touch.
            </EmptyState>
          )
        ) : (
          <div className="stat-grid">
            <Stat tone="accent" label="Definitions" value={data.targets} />
            <Stat label="Direct callers" value={data.direct_callers.length} />
            <Stat label="Indirect callers" value={data.indirect_callers.length} />
            <Stat
              tone="warn"
              label="Affected files"
              value={data.affected_files.length}
            />
          </div>
        )}
      </Panel>

      {data ? (
        <div className="two-col">
          <Panel title="Direct callers">
            <LocList items={data.direct_callers} onOpen={openLoc} />
          </Panel>
          <Panel title="Affected files">
            <LocList
              items={data.affected_files}
              onOpen={(p) => onOpenSource(p, 1)}
            />
          </Panel>
          <Panel title="Affected modules">
            <PlainList items={data.affected_modules} />
          </Panel>
          <Panel title="Affected tests">
            <LocList
              items={data.affected_tests}
              onOpen={(p) => onOpenSource(p, 1)}
            />
          </Panel>
        </div>
      ) : null}
    </div>
  );
}
