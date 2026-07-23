"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";

import type { JobSnapshot } from "@/lib/api";

type ButtonVariant = "default" | "accent" | "ghost" | "danger";

export function Button({
  variant = "default",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
  return <button className={`btn btn-${variant} ${className}`.trim()} {...props} />;
}

export function Panel({
  title,
  eyebrow,
  actions,
  children,
  className = "",
}: {
  title?: ReactNode;
  eyebrow?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`.trim()}>
      {(title || actions) && (
        <header className="panel-head">
          <div>
            {eyebrow ? <div className="eyebrow">{eyebrow}</div> : null}
            {title ? <h2 className="panel-title">{title}</h2> : null}
          </div>
          {actions ? <div className="panel-actions">{actions}</div> : null}
        </header>
      )}
      {children}
    </section>
  );
}

export function Stat({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: "default" | "accent" | "static" | "llm" | "warn";
}) {
  return (
    <div className={`stat stat-${tone}`}>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {hint ? <div className="stat-hint">{hint}</div> : null}
    </div>
  );
}

export function OriginBadge({ origin }: { origin: string }) {
  const isStatic = origin === "STATIC_ANALYSIS";
  return (
    <span
      className={`badge ${isStatic ? "badge-static" : "badge-llm"}`}
      title={isStatic ? "Deterministic static analysis" : "LLM inference"}
    >
      {isStatic ? "static" : "llm"}
    </span>
  );
}

export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "ok" | "warn" | "danger";
}) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="spinner" role="status" aria-live="polite">
      <span className="spinner-dot" aria-hidden="true" />
      {label ? <span className="spinner-label">{label}</span> : null}
    </span>
  );
}

export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <h3 className="empty-title">{title}</h3>
      {children ? <p className="empty-body">{children}</p> : null}
      {action ? <div className="empty-action">{action}</div> : null}
    </div>
  );
}

export function JobProgressBar({ job }: { job: JobSnapshot }) {
  const total = job.progress.total;
  const indeterminate = total == null;
  const pct = indeterminate
    ? 100
    : Math.min(100, Math.round((job.progress.done / Math.max(1, total)) * 100));
  const running = job.status === "running" || job.status === "pending";
  return (
    <div className="jobbar" data-status={job.status}>
      <div className="jobbar-track">
        <div
          className={`jobbar-fill${indeterminate && running ? " is-indeterminate" : ""}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="jobbar-meta mono">
        <span className="jobbar-status">{job.status}</span>
        <span className="jobbar-msg">
          {job.error
            ? job.error
            : job.progress.message || (running ? "working…" : "done")}
          {!indeterminate && running ? ` · ${job.progress.done}` : ""}
        </span>
      </div>
    </div>
  );
}
