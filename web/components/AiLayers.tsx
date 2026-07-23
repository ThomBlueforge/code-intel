"use client";

import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  type Config,
  type JobSnapshot,
  getConfig,
  pollJob,
  startEmbed,
  startEnrich,
} from "@/lib/api";
import { Button, JobProgressBar, Panel, Spinner } from "./ui";

type Kind = "enrich" | "embed";

interface Props {
  repoPath: string;
}

export function AiLayers({ repoPath }: Props) {
  const [config, setConfig] = useState<Config | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [job, setJob] = useState<JobSnapshot | null>(null);
  const [busy, setBusy] = useState<Kind | null>(null);
  const [force, setForce] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setConfig(null);
    getConfig(repoPath)
      .then((c) => {
        if (!cancelled) setConfig(c);
      })
      .catch(() => {
        /* config is best-effort */
      });
    return () => {
      cancelled = true;
    };
  }, [repoPath]);

  const run = useCallback(
    async (kind: Kind) => {
      setBusy(kind);
      setError(null);
      setJob(null);
      try {
        const start =
          kind === "enrich"
            ? await startEnrich({ path: repoPath, force })
            : await startEmbed({ path: repoPath, force });
        const final = await pollJob(start.id, setJob);
        if (final.status === "error") setError(final.error ?? "Job failed");
      } catch (err) {
        setError(err instanceof ApiError ? err.message : String(err));
      } finally {
        setBusy(null);
      }
    },
    [repoPath, force],
  );

  return (
    <div className="stack-lg">
      <Panel eyebrow="Optional AI layer" title="Enrichment & embeddings">
        <p className="muted">
          These layers are optional and never alter deterministic facts.
          Enrichment calls the configured local LLM; embeddings use the offline
          hashing provider into local Qdrant.
        </p>
        <div className="ai-actions">
          <label className="toggle">
            <input
              type="checkbox"
              checked={force}
              onChange={(event) => setForce(event.target.checked)}
            />
            <span>Force re-run</span>
          </label>
          <Button
            variant="accent"
            disabled={busy !== null}
            onClick={() => run("enrich")}
          >
            {busy === "enrich" ? <Spinner /> : "Enrich symbols"}
          </Button>
          <Button disabled={busy !== null} onClick={() => run("embed")}>
            {busy === "embed" ? <Spinner /> : "Embed"}
          </Button>
        </div>
        {error ? <div className="notice notice-danger">{error}</div> : null}
        {job ? (
          <div className="active-job">
            <div className="active-job-path mono">{busy ?? job.kind}</div>
            <JobProgressBar job={job} />
            {job.status === "done" && job.result ? (
              <div className="job-result mono">
                {Object.entries(job.result).map(([k, v]) => (
                  <span key={k}>
                    {k}={String(v)}
                  </span>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </Panel>

      <Panel eyebrow="Configuration" title="Effective settings">
        {!config ? (
          <div className="loading-block">
            <Spinner />
          </div>
        ) : (
          <table className="config-table">
            <tbody>
              <tr>
                <td>db_path</td>
                <td className="mono">{config.db_path}</td>
              </tr>
              <tr>
                <td>max_file_bytes</td>
                <td className="mono">{config.max_file_bytes}</td>
              </tr>
              <tr>
                <td>llm.base_url</td>
                <td className="mono">{config.llm.base_url}</td>
              </tr>
              <tr>
                <td>llm.model</td>
                <td className="mono">{config.llm.model}</td>
              </tr>
              <tr>
                <td>llm.temperature</td>
                <td className="mono">{config.llm.temperature}</td>
              </tr>
              <tr>
                <td>llm.max_tokens</td>
                <td className="mono">{config.llm.max_tokens}</td>
              </tr>
              <tr>
                <td>llm.max_concurrency</td>
                <td className="mono">{config.llm.max_concurrency}</td>
              </tr>
            </tbody>
          </table>
        )}
        <p className="ask-note">
          Configured via <span className="mono">CODE_INTEL_LLM_*</span> environment
          variables — no vendor lock-in.
        </p>
      </Panel>
    </div>
  );
}
