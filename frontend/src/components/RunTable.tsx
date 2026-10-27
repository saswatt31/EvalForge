"use client";

import Link from "next/link";

import { formatMs, formatPercent, formatScore, formatDate, runProgress } from "@/lib/format";
import type { RunSummary } from "@/lib/types";
import { StatusBadge, SourceBadge } from "./ui";
import { ArrowIcon } from "./icons";

export function RunTable({
  runs,
  dense = false,
  showDataset = false,
}: {
  runs: RunSummary[];
  dense?: boolean;
  showDataset?: boolean;
}) {
  return (
    <div className={`table-wrap ${dense ? "dense" : ""}`}>
      <table className="data-table run-table">
        <thead>
          <tr>
            <th scope="col">Run</th>
            <th scope="col">Status</th>
            <th scope="col">Context recall</th>
            <th scope="col">Faithfulness</th>
            <th scope="col">Relevance</th>
            <th scope="col">p95 latency</th>
            <th scope="col">Created</th>
            <th scope="col" aria-label="Open" />
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => {
            const completed = run.completed_queries + run.failed_queries;
            const inProgress = run.status === "running" || run.status === "queued";
            return (
              <tr key={run.id}>
                <td>
                  <div className="run-name-cell">
                    <Link href={`/runs/${run.id}`}>{run.name}</Link>
                    <span>
                      {[run.provider_name, run.model_name, `k=${String(run.pipeline_config.top_k ?? "—")}`]
                        .filter(Boolean)
                        .join(" · ")}
                      {showDataset ? ` · ${run.dataset_version_id.slice(0, 8)}` : ""}
                    </span>
                    <SourceBadge source={run.source} />
                  </div>
                </td>
                <td>
                  <StatusBadge status={run.status} />
                  {inProgress ? (
                    <div
                      className="mini-progress"
                      title={`${completed}/${run.total_queries} completed`}
                    >
                      <span
                        style={{
                          width: `${runProgress(
                            run.completed_queries,
                            run.failed_queries,
                            run.total_queries,
                          )}%`,
                        }}
                      />
                    </div>
                  ) : null}
                </td>
                <td className="numeric">{formatScore(run.metrics.context_recall.mean)}</td>
                <td className="numeric">{formatScore(run.metrics.faithfulness.mean)}</td>
                <td className="numeric">{formatScore(run.metrics.answer_relevance.mean)}</td>
                <td className="numeric">{formatMs(run.metrics.latency.p95_ms)}</td>
                <td className="date-cell">{formatDate(run.created_at)}</td>
                <td className="row-action">
                  <Link href={`/runs/${run.id}`} aria-label={`Open ${run.name}`}>
                    <ArrowIcon />
                  </Link>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="run-cards">
        {runs.map((run) => (
          <Link className="run-card" key={run.id} href={`/runs/${run.id}`}>
            <div className="run-card-top">
              <strong>{run.name}</strong>
              <StatusBadge status={run.status} />
            </div>
            <div className="run-card-meta">
              <SourceBadge source={run.source} />
              <span>
                {run.provider_name} · k={String(run.pipeline_config.top_k ?? "—")}
              </span>
              <span>{formatDate(run.created_at)}</span>
            </div>
            <div className="run-card-metrics">
              <span>
                Recall <b>{formatPercent(run.metrics.context_recall.mean)}</b>
              </span>
              <span>
                Faithful <b>{formatPercent(run.metrics.faithfulness.mean)}</b>
              </span>
              <span>
                p95 <b>{formatMs(run.metrics.latency.p95_ms)}</b>
              </span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
