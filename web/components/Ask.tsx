"use client";

import { type FormEvent, useState } from "react";

import { ApiError, type Answer, ask } from "@/lib/api";
import { Badge, Button, Panel, Spinner } from "./ui";

type OpenSource = (file: string, start?: number, end?: number) => void;

interface Props {
  repoPath: string;
  onOpenSource: OpenSource;
}

const CITE = /^(.+?):(\d+)/;

export function Ask({ repoPath, onOpenSource }: Props) {
  const [question, setQuestion] = useState("");
  const [useLlm, setUseLlm] = useState(false);
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    const q = question.trim();
    if (!q) return;
    setLoading(true);
    setError(null);
    setAnswer(null);
    try {
      setAnswer(await ask(repoPath, q, useLlm));
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
      <Panel eyebrow="Grounded Q&A" title="Ask">
        <form className="ask-form" onSubmit={onSubmit}>
          <textarea
            className="ask-input"
            rows={2}
            placeholder="Ask a question about this repository…"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
          />
          <div className="ask-controls">
            <label className="toggle">
              <input
                type="checkbox"
                checked={useLlm}
                onChange={(event) => setUseLlm(event.target.checked)}
              />
              <span>Use LLM</span>
            </label>
            <Button variant="accent" type="submit" disabled={loading}>
              {loading ? <Spinner /> : "Ask"}
            </Button>
          </div>
          <p className="ask-note">
            {useLlm
              ? "Answered by the configured local LLM, grounded strictly in retrieved context."
              : "Without the LLM, returns the cited context the answer would be grounded in."}
          </p>
        </form>
        {error ? <div className="notice notice-danger">{error}</div> : null}
      </Panel>

      {answer ? (
        <Panel
          title="Answer"
          actions={
            answer.used_llm ? (
              <Badge tone="ok">llm</Badge>
            ) : (
              <Badge>retrieval only</Badge>
            )
          }
        >
          <p className="answer-text">{answer.answer}</p>
          {answer.citations.length ? (
            <>
              <div className="eyebrow">Sources</div>
              <ul className="cite-list">
                {answer.citations.map((c, i) => {
                  const m = CITE.exec(c);
                  return (
                    <li key={`${c}-${i}`}>
                      {m ? (
                        <button
                          className="cite-row linkish mono"
                          onClick={() => onOpenSource(m[1], Number(m[2]))}
                        >
                          {c}
                        </button>
                      ) : (
                        <span className="cite-row mono">{c}</span>
                      )}
                    </li>
                  );
                })}
              </ul>
            </>
          ) : null}
        </Panel>
      ) : null}
    </div>
  );
}
