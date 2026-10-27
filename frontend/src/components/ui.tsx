"use client";

import Link from "next/link";
import { useState, type ReactNode } from "react";

import { ApiError } from "@/lib/api";
import { scoreTone, statusLabel } from "@/lib/format";
import type { RunSource, RunStatus } from "@/lib/types";
import { CheckIcon } from "./icons";

export function StatusBadge({ status }: { status: RunStatus }) {
  return (
    <span className={`status-badge status-${status}`}>
      <span className="status-dot" aria-hidden="true" />
      {statusLabel(status)}
    </span>
  );
}

export function SourceBadge({ source }: { source: RunSource }) {
  if (source === "demo") {
    return (
      <span className="source-badge source-demo" title="Simulated benchmark data">
        Synthetic demo
      </span>
    );
  }
  if (source === "cli") return <span className="source-badge">CLI</span>;
  if (source === "ci") return <span className="source-badge">GitHub Action</span>;
  return null;
}

export function ScoreValue({
  value,
  scale = "score",
}: {
  value: number | null;
  scale?: "score" | "percent";
}) {
  if (value === null) return <span className="metric-value neutral">n/a</span>;
  return (
    <span className={`metric-value ${scoreTone(value)}`}>
      {scale === "percent" ? `${(value * 100).toFixed(1)}%` : value.toFixed(3)}
    </span>
  );
}

export function MetricCard({
  label,
  value,
  hint,
  tone,
  children,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: "good" | "warn" | "bad" | "neutral";
  children?: ReactNode;
}) {
  return (
    <article className="metric-card">
      <span className="metric-label">{label}</span>
      <div className={`metric-number ${tone ?? "neutral"}`}>{value}</div>
      {hint ? <div className="metric-hint">{hint}</div> : null}
      {children}
    </article>
  );
}

export function Panel({
  title,
  aside,
  children,
  className = "",
}: {
  title?: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`.trim()}>
      {title || aside ? (
        <div className="panel-head">
          {title ? <h2>{title}</h2> : <span />}
          {aside}
        </div>
      ) : null}
      {children}
    </section>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
        <h1>{title}</h1>
        {description ? <p className="page-description">{description}</p> : null}
      </div>
      {actions ? <div className="page-actions">{actions}</div> : null}
    </header>
  );
}

export function EmptyState({
  title,
  description,
  action,
  secondaryAction,
}: {
  title: string;
  description: string;
  action?: ReactNode;
  secondaryAction?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <div className="empty-mark" aria-hidden="true">
        <CheckIcon />
      </div>
      <h3>{title}</h3>
      <p>{description}</p>
      {action || secondaryAction ? (
        <div className="empty-actions">
          {action}
          {secondaryAction}
        </div>
      ) : null}
    </div>
  );
}

export function LoadingBlock({ label = "Loading" }: { label?: string }) {
  return (
    <div className="loading-block" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span>{label}…</span>
    </div>
  );
}

export function ErrorNotice({ error, title = "Something went wrong" }: { error: unknown; title?: string }) {
  const message = error instanceof Error ? error.message : "The request failed.";
  const issues = error instanceof ApiError ? error.issues : [];
  return (
    <div className="error-notice" role="alert">
      <div>
        <strong>{title}</strong>
        <p>{message}</p>
        {issues.length ? (
          <ul>
            {issues.map((issue, index) => (
              <li key={`${issue.field ?? "issue"}-${index}`}>
                {issue.field ? <span>{issue.field}: </span> : null}
                {issue.message}
              </li>
            ))}
          </ul>
        ) : null}
        {error instanceof ApiError && error.status === 401 ? (
          <p className="error-help">
            Add the write API token from the sidebar, then retry.
          </p>
        ) : null}
        {error instanceof ApiError && error.status === 403 ? (
          <p className="error-help">This deployment is a read-only demo.</p>
        ) : null}
      </div>
    </div>
  );
}

export function CopyButton({ value, label = "Copy" }: { value: string; label?: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  return (
    <button className="copy-button" type="button" onClick={copy}>
      {copied ? "Copied" : label}
    </button>
  );
}

export function InlineLink({
  href,
  children,
}: {
  href: string;
  children: ReactNode;
}) {
  return (
    <Link className="inline-link" href={href}>
      {children}
    </Link>
  );
}
