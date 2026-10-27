"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { cancelRun } from "@/lib/api";
import { useRun } from "@/lib/hooks";
import {
  formatDate,
  formatPercent,
  isActiveStatus,
  runDuration,
  runProgress,
  shortId,
} from "@/lib/format";
import type { RunSummary } from "@/lib/types";
import { QueryResults } from "@/components/QueryResults";
import { RunMetrics } from "@/components/RunMetrics";
import { ArrowIcon, CompareIcon } from "@/components/icons";
import {
  CopyButton,
  ErrorNotice,
  LoadingBlock,
  PageHeader,
  Panel,
  SourceBadge,
  StatusBadge,
} from "@/components/ui";

function RunConfiguration({ run }: { run: RunSummary }) {
  const target = run.target_kind === "http" ? "HTTP endpoint" : "Reference RAG";
  const headerNames = Array.isArray(run.target_config.header_names)
    ? run.target_config.header_names.join(", ")
    : null;
  return (
    <Panel title="Run configuration" className="config-panel">
      <dl className="config-list">
        <div>
          <dt>Target</dt>
          <dd>{target}</dd>
        </div>
        <div>
          <dt>Provider</dt>
          <dd>{run.provider_name}</dd>
        </div>
        <div>
          <dt>Model</dt>
          <dd>{run.model_name ?? "—"}</dd>
        </div>
        <div>
          <dt>Top-k</dt>
          <dd>{String(run.pipeline_config.top_k ?? "—")}</dd>
        </div>
        <div>
          <dt>Judge</dt>
          <dd>
            {run.judge_mode === "mock" ? "Mock lexical" : "Ragas LLM"} · {run.judge_model}
          </dd>
        </div>
        <div>
          <dt>Judge repeats</dt>
          <dd>{run.judge_repeats}</dd>
        </div>
        <div>
          <dt>Warmups</dt>
          <dd>{run.warmup_count}</dd>
        </div>
        <div>
          <dt>Dataset version</dt>
          <dd>
            <code>{shortId(run.dataset_version_id, 12)}</code>
          </dd>
        </div>
        {headerNames ? (
          <div>
            <dt>Target headers</dt>
            <dd>{headerNames} (values redacted)</dd>
          </div>
        ) : null}
        <div>
          <dt>Started</dt>
          <dd>{formatDate(run.started_at)}</dd>
        </div>
        <div>
          <dt>Finished</dt>
          <dd>{formatDate(run.finished_at)}</dd>
        </div>
        <div>
          <dt>Duration</dt>
          <dd>{runDuration(run.started_at, run.finished_at)}</dd>
        </div>
      </dl>
      <div className="config-hash">
        <span>Config hash</span>
        <code>{run.config_hash}</code>
        <CopyButton value={run.config_hash} />
      </div>
      {run.baseline_run_id ? (
        <Link
          className="text-link"
          href={`/compare?baseline=${run.baseline_run_id}&candidate=${run.id}`}
        >
          <CompareIcon /> Compare with baseline
        </Link>
      ) : null}
    </Panel>
  );
}

export default function RunDetailPage() {
  const params = useParams<{ id: string }>();
  const runId = params.id;
  const { data: run, error, isLoading, mutate } = useRun(runId);
  const [cancelling, setCancelling] = useState(false);
  const [cancelError, setCancelError] = useState<unknown>(null);

  async function cancel() {
    if (!run || !window.confirm("Cancel this run? Completed query results are retained.")) return;
    setCancelling(true);
    setCancelError(null);
    try {
      await cancelRun(run.id);
      await mutate();
    } catch (errorValue) {
      setCancelError(errorValue);
    } finally {
      setCancelling(false);
    }
  }

  if (isLoading) return <LoadingBlock label="Loading run" />;
  if (error) return <ErrorNotice error={error} title="Could not load this run" />;
  if (!run) return <ErrorNotice error={new Error("Run not found")} />;

  const active = isActiveStatus(run.status);
  const progress = runProgress(run.completed_queries, run.failed_queries, run.total_queries);
  const isDemo = run.source === "demo";

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow={`Run · ${shortId(run.id)}`}
        title={run.name}
        description={
          <span className="header-meta">
            <StatusBadge status={run.status} />
            <SourceBadge source={run.source} />
            <span>{run.provider_name}</span>
            <span>top-{String(run.pipeline_config.top_k ?? "—")}</span>
            <span>{formatDate(run.created_at)}</span>
          </span>
        }
        actions={
          <>
            {active ? (
              <button
                className="button secondary"
                type="button"
                onClick={() => void cancel()}
                disabled={cancelling}
              >
                {cancelling ? "Cancelling…" : "Cancel run"}
              </button>
            ) : null}
            <Link className="button primary" href={`/compare?candidate=${run.id}`}>
              <CompareIcon /> Compare
            </Link>
          </>
        }
      />

      {isDemo ? (
        <div className="notice demo-notice">
          <strong>Synthetic demo run.</strong> Answers were generated from the bundled corpus and
          scored by the deterministic mock judge. Latency and TTFT values are simulated.
        </div>
      ) : null}

      {active ? (
        <div className="run-progress panel">
          <div>
            <strong>
              {run.status === "queued" ? "Queued" : "Evaluating"}{" "}
              {run.completed_queries + run.failed_queries}/{run.total_queries}
            </strong>
            <span>
              {run.failed_queries} failed · refreshes automatically
            </span>
          </div>
          <div className="progress-track" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>
            <span style={{ width: `${progress}%` }} />
          </div>
        </div>
      ) : null}

      {run.error_message ? (
        <div className="error-notice" role="alert">
          <div>
            <strong>Run error</strong>
            <p>{run.error_message}</p>
          </div>
        </div>
      ) : null}
      {cancelError ? <ErrorNotice error={cancelError} title="Could not cancel the run" /> : null}

      {run.status === "failed" && run.completed_queries === 0 ? (
        <div className="blank-run">
          <h2>No successful query results</h2>
          <p>
            The target did not return any usable answers. Review the error above and the run
            configuration, then start a new run.
          </p>
          <Link className="button primary" href="/runs/new">
            Start another run <ArrowIcon />
          </Link>
        </div>
      ) : (
        <>
          <RunMetrics metrics={run.metrics} demo={isDemo} />
          <div className="run-detail-grid">
            <QueryResults runId={run.id} active={active} />
            <RunConfiguration run={run} />
          </div>
        </>
      )}

      {run.status === "partial" ? (
        <div className="notice">
          <strong>Partial run.</strong> {run.failed_queries} of {run.total_queries} queries failed;
          quality aggregates only include successful results. Success rate is{" "}
          {formatPercent(run.metrics.success_rate)}.
        </div>
      ) : null}
    </div>
  );
}
