"use client";

import {
  formatMs,
  formatNumber,
  formatPercent,
  formatScore,
  metricScoreTone,
} from "@/lib/format";
import type { LatencyAggregate, MetricAggregate, RunMetrics as Metrics } from "@/lib/types";
import { MetricCard } from "./ui";

function QualityMetric({
  label,
  metricName,
  metric,
}: {
  label: string;
  metricName: string;
  metric: MetricAggregate;
}) {
  const tone = metricScoreTone(metricName, metric.mean);
  return (
    <MetricCard
      label={label}
      tone={tone}
      value={formatScore(metric.mean)}
      hint={`${metric.judged_queries} queries · ${metric.failed_samples} failed samples`}
    >
      <div className="metric-track" aria-hidden="true">
        <span style={{ width: `${(metric.mean ?? 0) * 100}%` }} />
      </div>
    </MetricCard>
  );
}

function TtftProvenance({ latency }: { latency: LatencyAggregate }) {
  const total =
    latency.measured_ttft_count + latency.target_reported_ttft_count + latency.demo_ttft_count;
  if (total === 0) return <>No TTFT samples</>;
  return (
    <>
      {latency.measured_ttft_count > 0
        ? `${latency.measured_ttft_count} measured`
        : null}
      {latency.target_reported_ttft_count > 0
        ? `${latency.measured_ttft_count > 0 ? " · " : ""}${latency.target_reported_ttft_count} target-reported`
        : null}
      {latency.demo_ttft_count > 0
        ? `${latency.measured_ttft_count + latency.target_reported_ttft_count > 0 ? " · " : ""}${latency.demo_ttft_count} simulated`
        : null}
    </>
  );
}

export function RunMetrics({ metrics, demo = false }: { metrics: Metrics; demo?: boolean }) {
  const latency = metrics.latency;
  const ttftMissing = latency.ttft_p50_ms === null;
  return (
    <div className="metrics-layout">
      <section className="quality-grid">
        <QualityMetric
          label="Context recall"
          metricName="context_recall"
          metric={metrics.context_recall}
        />
        <QualityMetric
          label="Faithfulness"
          metricName="faithfulness"
          metric={metrics.faithfulness}
        />
        <QualityMetric
          label="Answer relevance"
          metricName="answer_relevance"
          metric={metrics.answer_relevance}
        />
        <QualityMetric
          label="Hallucination rate"
          metricName="hallucination_rate"
          metric={metrics.hallucination_rate}
        />
      </section>

      <section className="latency-panel panel">
        <div className="panel-head">
          <h2>Latency &amp; throughput</h2>
          <span className="panel-note">
            {metrics.success_rate === null ? "No query data" : `${formatPercent(metrics.success_rate)} success`}
          </span>
        </div>
        <div className="latency-stats">
          <div>
            <span>p50</span>
            <strong>{formatMs(latency.p50_ms)}</strong>
          </div>
          <div>
            <span>p95</span>
            <strong>{formatMs(latency.p95_ms)}</strong>
          </div>
          <div>
            <span>mean</span>
            <strong>{formatMs(latency.mean_ms)}</strong>
          </div>
          <div>
            <span>tokens/sec</span>
            <strong>{formatNumber(latency.mean_tokens_per_second)}</strong>
          </div>
        </div>
        <div className="ttft-row">
          <div>
            <span>Time to first token</span>
            <strong>
              {formatMs(latency.ttft_p50_ms)} <small>p50</small>
              {latency.ttft_p95_ms !== null ? (
                <>
                  {" · "}
                  {formatMs(latency.ttft_p95_ms)} <small>p95</small>
                </>
              ) : null}
            </strong>
          </div>
          <p className={ttftMissing ? "panel-note" : "provenance"}>
            {ttftMissing ? "No TTFT samples were recorded for this run." : <TtftProvenance latency={latency} />}
            {demo ? " Demo timings are simulated and must not be read as product performance." : ""}
          </p>
        </div>
        <div className="cache-row">
          <span>Judge cache</span>
          <span>
            <b>{metrics.cache_hits}</b> hits · <b>{metrics.cache_misses}</b> misses
          </span>
        </div>
      </section>
    </div>
  );
}
