"use client";

import Link from "next/link";

import { useDatasets, useMeta, useRuns } from "@/lib/hooks";
import {
  formatMs,
  formatPercent,
  formatScore,
  scoreTone,
  shortId,
} from "@/lib/format";
import type { RunSummary } from "@/lib/types";
import { RunTable } from "@/components/RunTable";
import {
  EmptyState,
  ErrorNotice,
  LoadingBlock,
  PageHeader,
  Panel,
  SourceBadge,
  StatusBadge,
} from "@/components/ui";
import { ArrowIcon, DatasetIcon, PlusIcon, RunsIcon } from "@/components/icons";

function latestQuality(run: RunSummary | undefined) {
  if (!run) return null;
  const values = [
    run.metrics.context_recall.mean,
    run.metrics.faithfulness.mean,
    run.metrics.answer_relevance.mean,
  ].filter((value): value is number => value !== null);
  if (!values.length) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

export default function OverviewPage() {
  const { data: meta, error: metaError } = useMeta();
  const { data: runsPage, error: runsError } = useRuns({ limit: 8 });
  const { data: datasets, error: datasetsError } = useDatasets();

  const latest = runsPage?.items[0];
  const quality = latestQuality(latest);
  const liveRuns = runsPage?.items.filter(
    (run) => run.status === "running" || run.status === "queued",
  ).length;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Evaluation workspace"
        title={
          <>
            Measure what your <span className="accent-text">RAG actually does.</span>
          </>
        }
        description="Run golden datasets against a reference pipeline or your own HTTP endpoint. Inspect quality, missed contexts, and tail latency—then compare every release to a baseline."
        actions={
          <>
            <Link className="button primary" href="/runs/new">
              <PlusIcon /> New evaluation
            </Link>
            <Link className="button secondary" href="/datasets">
              <DatasetIcon /> Import dataset
            </Link>
          </>
        }
      />

      {metaError ? (
        <ErrorNotice
          error={metaError}
          title="The API is not reachable"
        />
      ) : null}

      {meta?.demo_mode ? (
        <div className="notice">
          <strong>Read-only demonstration.</strong> All runs below are generated from a synthetic
          corpus with a deterministic lexical judge. Timings are simulated and marked in the UI.
        </div>
      ) : null}

      <section className="stat-grid" aria-label="Workspace summary">
        <div className="stat-card">
          <span>Total runs</span>
          <strong>{runsPage?.total ?? "—"}</strong>
          <small>{liveRuns ? `${liveRuns} active now` : "No active runs"}</small>
        </div>
        <div className="stat-card">
          <span>Latest quality</span>
          <strong className={scoreTone(quality)}>{quality === null ? "n/a" : formatScore(quality)}</strong>
          <small>Mean of recall, faithfulness and relevance</small>
        </div>
        <div className="stat-card">
          <span>Latest p95 latency</span>
          <strong>{formatMs(latest?.metrics.latency.p95_ms)}</strong>
          <small>Target response distribution</small>
        </div>
        <div className="stat-card">
          <span>Datasets</span>
          <strong>{datasets?.length ?? "—"}</strong>
          <small>
            {datasets?.reduce((sum, dataset) => sum + dataset.latest_version.item_count, 0) ?? "—"}{" "}
            latest-version queries
          </small>
        </div>
      </section>

      <div className="overview-grid">
        <Panel
          className="recent-runs"
          title="Recent runs"
          aside={
            <Link className="text-link" href="/runs">
              All runs <ArrowIcon />
            </Link>
          }
        >
          {runsError ? <ErrorNotice error={runsError} title="Could not load runs" /> : null}
          {!runsPage && !runsError ? <LoadingBlock label="Loading runs" /> : null}
          {runsPage && runsPage.items.length === 0 ? (
            <EmptyState
              title="No benchmark runs yet"
              description="Import a dataset and start an offline mock evaluation. You can connect an HTTP RAG endpoint once the local flow works."
              action={
                <Link className="button primary" href="/runs/new">
                  Start an evaluation
                </Link>
              }
              secondaryAction={
                <Link className="button secondary" href="/datasets">
                  Import a dataset
                </Link>
              }
            />
          ) : null}
          {runsPage?.items.length ? <RunTable runs={runsPage.items} dense /> : null}
        </Panel>

        <aside className="overview-side">
          {latest ? (
            <Panel
              title="Latest run"
              aside={<StatusBadge status={latest.status} />}
              className="latest-card"
            >
              <Link className="latest-title" href={`/runs/${latest.id}`}>
                {latest.name}
              </Link>
              <div className="latest-meta">
                <SourceBadge source={latest.source} />
                <span>{latest.provider_name}</span>
                <span>k={String(latest.pipeline_config.top_k ?? "—")}</span>
              </div>
              <dl className="mini-metrics">
                <div>
                  <dt>Recall</dt>
                  <dd>{formatPercent(latest.metrics.context_recall.mean)}</dd>
                </div>
                <div>
                  <dt>Faithfulness</dt>
                  <dd>{formatPercent(latest.metrics.faithfulness.mean)}</dd>
                </div>
                <div>
                  <dt>Relevance</dt>
                  <dd>{formatPercent(latest.metrics.answer_relevance.mean)}</dd>
                </div>
                <div>
                  <dt>p95</dt>
                  <dd>{formatMs(latest.metrics.latency.p95_ms)}</dd>
                </div>
              </dl>
              <div className="latest-footer">
                <span>Dataset {shortId(latest.dataset_version_id)}</span>
                <Link className="text-link" href={`/runs/${latest.id}`}>
                  Inspect run <ArrowIcon />
                </Link>
              </div>
            </Panel>
          ) : (
            <Panel title="Workflow" className="workflow-card">
              <ol className="workflow-list">
                <li>
                  <span>01</span>
                  <div>
                    <strong>Bring a golden dataset</strong>
                    <p>Upload JSONL with questions, answers, and reference contexts.</p>
                  </div>
                </li>
                <li>
                  <span>02</span>
                  <div>
                    <strong>Choose a target</strong>
                    <p>Use the bundled RAG reference or point at any streaming endpoint.</p>
                  </div>
                </li>
                <li>
                  <span>03</span>
                  <div>
                    <strong>Compare the evidence</strong>
                    <p>Review per-query judgments, latency percentiles, and regressions.</p>
                  </div>
                </li>
              </ol>
            </Panel>
          )}

          <Panel title="Datasets" aside={<DatasetIcon />} className="dataset-glance">
            {datasetsError ? (
              <p className="muted-copy">Could not load datasets.</p>
            ) : datasets?.length ? (
              <div className="dataset-links">
                {datasets.slice(0, 4).map((dataset) => (
                  <Link key={dataset.id} href={`/datasets/${dataset.id}`}>
                    <div>
                      <strong>{dataset.name}</strong>
                      <span>
                        v{dataset.latest_version.version_number} ·{" "}
                        {dataset.latest_version.item_count} queries
                      </span>
                    </div>
                    <ArrowIcon />
                  </Link>
                ))}
              </div>
            ) : (
              <p className="muted-copy">No datasets imported yet.</p>
            )}
            <Link className="text-link" href="/datasets">
              <RunsIcon /> Manage datasets
            </Link>
          </Panel>
        </aside>
      </div>
    </div>
  );
}
