"use client";

import Link from "next/link";
import { useState } from "react";

import { useRuns } from "@/lib/hooks";
import { formatMs, formatPercent } from "@/lib/format";
import type { RunStatus } from "@/lib/types";
import { RunTable } from "@/components/RunTable";
import {
  EmptyState,
  ErrorNotice,
  LoadingBlock,
  PageHeader,
  Panel,
} from "@/components/ui";
import { PlusIcon, RefreshIcon } from "@/components/icons";

const statuses: Array<{ value: RunStatus | "all"; label: string }> = [
  { value: "all", label: "All" },
  { value: "running", label: "Running" },
  { value: "queued", label: "Queued" },
  { value: "succeeded", label: "Succeeded" },
  { value: "partial", label: "Partial" },
  { value: "failed", label: "Failed" },
  { value: "cancelled", label: "Cancelled" },
];

export default function RunsPage() {
  const [status, setStatus] = useState<RunStatus | "all">("all");
  const { data, error, isLoading, mutate, isValidating } = useRuns({
    limit: 100,
    status: status === "all" ? undefined : status,
  });

  const succeeded = data?.items.filter((run) => run.status === "succeeded").length ?? 0;
  const failed = data?.items.filter((run) => run.status === "failed").length ?? 0;
  const meanP95 = (() => {
    const values =
      data?.items
        .map((run) => run.metrics.latency.p95_ms)
        .filter((value): value is number => value !== null) ?? [];
    if (!values.length) return null;
    return values.reduce((sum, value) => sum + value, 0) / values.length;
  })();

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Run history"
        title="Every benchmark, with its receipts."
        description="Runs are immutable snapshots of dataset version, target configuration, judge settings, and per-query evidence."
        actions={
          <Link className="button primary" href="/runs/new">
            <PlusIcon /> New evaluation
          </Link>
        }
      />

      <div className="summary-strip">
        <span>
          <b>{data?.total ?? "—"}</b> runs
        </span>
        <span>
          <b>{succeeded}</b> succeeded
        </span>
        <span>
          <b>{failed}</b> failed
        </span>
        <span>
          mean p95 <b>{formatMs(meanP95)}</b>
        </span>
        <button
          className="icon-button refresh-button"
          type="button"
          onClick={() => void mutate()}
          aria-label="Refresh runs"
          disabled={isValidating}
        >
          <RefreshIcon />
        </button>
      </div>

      <Panel>
        <div className="filter-row">
          <div className="segmented" role="group" aria-label="Filter runs by status">
            {statuses.map((option) => (
              <button
                key={option.value}
                type="button"
                className={status === option.value ? "selected" : ""}
                onClick={() => setStatus(option.value)}
              >
                {option.label}
              </button>
            ))}
          </div>
          <span className="panel-note">
            Showing {data?.items.length ?? 0} of {data?.total ?? 0}
          </span>
        </div>

        {error ? <ErrorNotice error={error} title="Could not load runs" /> : null}
        {isLoading ? <LoadingBlock label="Loading run history" /> : null}
        {data && data.items.length === 0 ? (
          <EmptyState
            title={status === "all" ? "No runs yet" : `No ${status} runs`}
            description={
              status === "all"
                ? "Start with the bundled sample dataset and the offline reference target."
                : "Change the status filter or start a new evaluation."
            }
            action={
              <Link className="button primary" href="/runs/new">
                Start an evaluation
              </Link>
            }
            secondaryAction={
              status !== "all" ? (
                <button className="button secondary" type="button" onClick={() => setStatus("all")}>
                  Clear filter
                </button>
              ) : undefined
            }
          />
        ) : null}
        {data?.items.length ? <RunTable runs={data.items} showDataset /> : null}
      </Panel>

      <div className="explain-row">
        <div>
          <span>Quality</span>
          <p>
            Macro-averaged over successfully judged queries. Failed judge samples are counted and
            excluded, never replaced with zero.
          </p>
        </div>
        <div>
          <span>Latency</span>
          <p>
            p50 and p95 come from persisted per-query measurements. Demo values are explicitly
            simulated; target-reported TTFT is labelled separately.
          </p>
        </div>
        <div>
          <span>Latest score</span>
          <p>
            {data?.items[0]
              ? `${formatPercent(data.items[0].metrics.faithfulness.mean)} faithfulness on ${
                  data.items[0].name
                }.`
              : "No score available until a run completes."}
          </p>
        </div>
      </div>
    </div>
  );
}
