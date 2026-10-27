"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";

import { useComparison, useRuns } from "@/lib/hooks";
import {
  formatDelta,
  formatMs,
  formatPercent,
  formatScore,
  metricLabel,
  metricUnit,
  shortId,
} from "@/lib/format";
import type { CompareRow, RunSummary } from "@/lib/types";
import {
  EmptyState,
  ErrorNotice,
  LoadingBlock,
  PageHeader,
  Panel,
  SourceBadge,
  StatusBadge,
} from "./ui";
import { CompareIcon } from "./icons";

const LOWER_IS_BETTER = new Set([
  "hallucination_rate",
  "latency_p50_ms",
  "latency_p95_ms",
  "ttft_p50_ms",
  "ttft_p95_ms",
]);
const REGRESSION_THRESHOLD = 0.005;
const LATENCY_REGRESSION_MS = 1;
const QUALITY_METRICS = new Set([
  "context_recall",
  "faithfulness",
  "answer_relevance",
  "hallucination_rate",
  "success_rate",
]);

function deltaTone(row: CompareRow): "good" | "bad" | "neutral" {
  if (row.delta === null) return "neutral";
  const threshold = metricUnit(row.metric) === "ms" ? LATENCY_REGRESSION_MS : REGRESSION_THRESHOLD;
  if (Math.abs(row.delta) < threshold) return "neutral";
  const improved = LOWER_IS_BETTER.has(row.metric) ? row.delta < 0 : row.delta > 0;
  return improved ? "good" : "bad";
}

function valueFor(metric: string, value: number | null): string {
  if (value === null) return "n/a";
  if (metricUnit(metric) === "ms") return formatMs(value);
  if (metricUnit(metric) === "rate") return value.toFixed(1);
  return metric === "success_rate" ? formatPercent(value) : formatScore(value);
}

function deltaFor(row: CompareRow): string {
  if (row.delta === null) return "n/a";
  if (metricUnit(row.metric) === "ms") {
    return `${row.delta >= 0 ? "+" : ""}${row.delta.toFixed(0)} ms`;
  }
  if (metricUnit(row.metric) === "rate") return formatDelta(row.delta, 1);
  return `${row.delta >= 0 ? "+" : ""}${(row.delta * 100).toFixed(2)} pp`;
}

function RunSelector({
  label,
  value,
  onChange,
  runs,
  exclude,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  runs: RunSummary[];
  exclude?: string;
}) {
  return (
    <label className="field compare-select">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">Choose a run…</option>
        {runs
          .filter((run) => run.id !== exclude)
          .map((run) => (
            <option key={run.id} value={run.id}>
              {run.name} · {run.status} · {shortId(run.id)}
            </option>
          ))}
      </select>
    </label>
  );
}

function CompareSide({
  run,
  label,
}: {
  run: RunSummary;
  label: string;
}) {
  const qualityValues = [
    run.metrics.context_recall.mean,
    run.metrics.faithfulness.mean,
    run.metrics.answer_relevance.mean,
  ].filter((value): value is number => value !== null);
  const quality = qualityValues.length
    ? qualityValues.reduce((sum, value) => sum + value, 0) / qualityValues.length
    : null;
  return (
    <article className="compare-run-card">
      <span>{label}</span>
      <Link href={`/runs/${run.id}`}>{run.name}</Link>
      <div className="compare-run-meta">
        <StatusBadge status={run.status} />
        <SourceBadge source={run.source} />
        <span>{formatPercent(quality)} mean quality</span>
      </div>
      <dl>
        <div>
          <dt>Faithfulness</dt>
          <dd>{formatPercent(run.metrics.faithfulness.mean)}</dd>
        </div>
        <div>
          <dt>Context recall</dt>
          <dd>{formatPercent(run.metrics.context_recall.mean)}</dd>
        </div>
        <div>
          <dt>p95 latency</dt>
          <dd>{formatMs(run.metrics.latency.p95_ms)}</dd>
        </div>
        <div>
          <dt>Config</dt>
          <dd>{shortId(run.config_hash, 10)}</dd>
        </div>
      </dl>
    </article>
  );
}

function ComparisonTable({ rows, title }: { rows: CompareRow[]; title: string }) {
  if (!rows.length) return null;
  return (
    <div className="compare-table-block">
      <h3>{title}</h3>
      <div className="table-wrap">
        <table className="data-table compare-table">
          <thead>
            <tr>
              <th scope="col">Metric</th>
              <th scope="col">Baseline</th>
              <th scope="col">Candidate</th>
              <th scope="col">Delta</th>
              <th scope="col">Direction</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const tone = deltaTone(row);
              return (
                <tr key={row.metric}>
                  <th scope="row">{metricLabel(row.metric)}</th>
                  <td className="numeric">{valueFor(row.metric, row.baseline)}</td>
                  <td className="numeric">{valueFor(row.metric, row.candidate)}</td>
                  <td className={`numeric delta ${tone}`}>{deltaFor(row)}</td>
                  <td>
                    <span className={`direction ${tone}`}>
                      {tone === "good" ? "Improved" : tone === "bad" ? "Regressed" : "Unchanged"}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function CompareView() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [baselineId, setBaselineId] = useState(searchParams.get("baseline") ?? "");
  const [candidateId, setCandidateId] = useState(searchParams.get("candidate") ?? "");
  const { data: runsPage, error: runsError, isLoading: runsLoading } = useRuns({ limit: 100 });
  const { data: comparison, error, isLoading } = useComparison(baselineId, candidateId);

  const runs = runsPage?.items ?? [];

  function syncUrl(nextBaseline: string, nextCandidate: string) {
    const params = new URLSearchParams();
    if (nextBaseline) params.set("baseline", nextBaseline);
    if (nextCandidate) params.set("candidate", nextCandidate);
    const next = params.toString();
    router.replace(next ? `/compare?${next}` : "/compare", { scroll: false });
  }

  function chooseBaseline(value: string) {
    setBaselineId(value);
    syncUrl(value, candidateId);
  }

  function chooseCandidate(value: string) {
    setCandidateId(value);
    syncUrl(baselineId, value);
  }

  const { qualityRows, latencyRows, regressions, improvements } = useMemo(() => {
    const rows = comparison?.rows ?? [];
    return {
      qualityRows: rows.filter((row) => QUALITY_METRICS.has(row.metric)),
      latencyRows: rows.filter((row) => !QUALITY_METRICS.has(row.metric)),
      regressions: rows.filter((row) => deltaTone(row) === "bad").length,
      improvements: rows.filter((row) => deltaTone(row) === "good").length,
    };
  }, [comparison]);

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Regression review"
        title="Compare the evidence."
        description="Baseline and candidate metrics come from separate persisted runs. Judge the change against the measured delta, not a single aggregate."
        actions={
          <Link className="button secondary" href="/runs">
            Browse runs
          </Link>
        }
      />

      {runsError ? <ErrorNotice error={runsError} title="Could not load runs" /> : null}
      {runsLoading ? <LoadingBlock label="Loading runs" /> : null}
      {runsPage && runs.length === 0 ? (
        <Panel>
          <EmptyState
            title="Nothing to compare yet"
            description="Finish at least two evaluations to compare quality and latency."
            action={
              <Link className="button primary" href="/runs/new">
                Start an evaluation
              </Link>
            }
          />
        </Panel>
      ) : (
        <>
          <Panel className="compare-picker">
            <div className="compare-picker-grid">
              <RunSelector
                label="Baseline"
                value={baselineId}
                onChange={chooseBaseline}
                runs={runs}
                exclude={candidateId}
              />
              <div className="compare-arrow" aria-hidden="true">
                <CompareIcon />
              </div>
              <RunSelector
                label="Candidate"
                value={candidateId}
                onChange={chooseCandidate}
                runs={runs}
                exclude={baselineId}
              />
            </div>
          </Panel>

          {!baselineId || !candidateId ? (
            <div className="compare-placeholder">
              Choose a baseline and a candidate to see metric deltas. Lower hallucination and
              latency are improvements; higher quality scores are improvements.
            </div>
          ) : null}

          {error ? <ErrorNotice error={error} title="Could not compare these runs" /> : null}
          {isLoading && baselineId && candidateId ? <LoadingBlock label="Comparing runs" /> : null}

          {comparison ? (
            <>
              <section className="compare-hero">
                <CompareSide run={comparison.baseline} label="Baseline" />
                <div className="compare-verdict">
                  <span className={`verdict-number ${regressions ? "bad" : "good"}`}>
                    {regressions > 0 ? `${regressions} regression${regressions === 1 ? "" : "s"}` : "No regressions"}
                  </span>
                  <p>
                    {improvements} improvement{improvements === 1 ? "" : "s"} detected.{" "}
                    {regressions > 0
                      ? "Review the regressed metrics before shipping."
                      : "Metrics are unchanged or improved within the display threshold."}
                  </p>
                </div>
                <CompareSide run={comparison.candidate} label="Candidate" />
              </section>

              <Panel className="compare-results">
                <ComparisonTable rows={qualityRows} title="Quality" />
                <ComparisonTable rows={latencyRows} title="Latency &amp; throughput" />
                <p className="compare-footnote">
                  Quality deltas are percentage points; n/a means the metric had no successful
                  samples in one of the runs. A threshold of 0.5 pp (or 1 ms) is used only for
                  labelling, not for statistical significance.
                </p>
              </Panel>
            </>
          ) : null}
        </>
      )}
    </div>
  );
}
