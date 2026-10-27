"use client";

import { useMemo, useState } from "react";

import { useRunResults } from "@/lib/hooks";
import { formatMs, formatPercent, formatScore, metricScoreTone } from "@/lib/format";
import type { MetricScore, QueryResult } from "@/lib/types";
import { ChevronIcon, SearchIcon } from "./icons";
import { ErrorNotice, LoadingBlock, Panel } from "./ui";

const PAGE_SIZE = 10;

function groupedMetrics(scores: MetricScore[]) {
  const grouped = new Map<string, MetricScore[]>();
  for (const score of scores) {
    const values = grouped.get(score.metric_name) ?? [];
    values.push(score);
    grouped.set(score.metric_name, values);
  }
  return grouped;
}

function averageScores(scores: MetricScore[]): number | null {
  const values = scores.map((score) => score.score).filter((score): score is number => score !== null);
  if (!values.length) return null;
  return values.reduce((sum, score) => sum + score, 0) / values.length;
}

function ResultDetails({ result }: { result: QueryResult }) {
  const grouped = groupedMetrics(result.metrics);
  return (
    <div className="result-details">
      <div className="result-columns">
        <div>
          <h4>Generated answer</h4>
          <p className="answer-copy">{result.answer ?? "No answer was returned."}</p>
        </div>
        <div>
          <h4>Reference answer</h4>
          <p className="muted-copy">{result.ground_truth}</p>
        </div>
      </div>

      <div className="result-metrics">
        {Array.from(grouped.entries()).map(([metric, scores]) => (
          <div className="result-metric" key={metric}>
            <div>
              <span>{metric.replaceAll("_", " ")}</span>
              <strong className={metricScoreTone(metric, averageScores(scores))}>
                {formatScore(averageScores(scores))}
              </strong>
            </div>
            <ul>
              {scores.map((score) => (
                <li key={score.id}>
                  <span>Sample {score.sample_index + 1}</span>
                  <span className={metricScoreTone(metric, score.score)}>
                    {score.status === "failed" ? "failed" : formatScore(score.score)}
                  </span>
                  {score.judge_cached ? <em>cached</em> : null}
                  {score.reason ? <p>{score.reason}</p> : null}
                  {score.error_message ? <p className="error-copy">{score.error_message}</p> : null}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <div className="context-list">
        <h4>Retrieved contexts</h4>
        {result.contexts.length ? (
          result.contexts.map((context, index) => (
            <article key={`${result.id}-context-${index}`}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <p>{context}</p>
            </article>
          ))
        ) : (
          <p className="muted-copy">No contexts were returned.</p>
        )}
      </div>
      {result.error_message ? (
        <p className="error-copy">
          <strong>Target error:</strong> {result.error_message}
        </p>
      ) : null}
    </div>
  );
}

export function QueryResults({ runId, active }: { runId: string; active: boolean }) {
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<"all" | "succeeded" | "failed">("all");
  const { data, error, isLoading } = useRunResults(runId, {
    limit: PAGE_SIZE,
    offset,
    active,
  });

  const visible = useMemo(() => {
    if (!data) return [];
    const query = search.trim().toLowerCase();
    return data.items.filter((item) => {
      if (status !== "all" && item.status !== status) return false;
      if (!query) return true;
      return (
        item.question.toLowerCase().includes(query) ||
        (item.answer ?? "").toLowerCase().includes(query)
      );
    });
  }, [data, search, status]);

  if (isLoading) return <LoadingBlock label="Loading query results" />;
  if (error) return <ErrorNotice error={error} title="Could not load results" />;

  return (
    <Panel
      className="results-panel"
      title="Query results"
      aside={<span className="panel-note">{data?.total ?? 0} queries</span>}
    >
      <div className="result-toolbar">
        <label className="search-field">
          <SearchIcon />
          <span className="sr-only">Search questions and answers</span>
          <input
            type="search"
            placeholder="Search questions and answers…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>
        <div className="segmented" role="group" aria-label="Filter by query status">
          {(["all", "succeeded", "failed"] as const).map((value) => (
            <button
              key={value}
              type="button"
              className={status === value ? "selected" : ""}
              onClick={() => setStatus(value)}
            >
              {value}
            </button>
          ))}
        </div>
      </div>

      {visible.length ? (
        <div className="results-list">
          {visible.map((result) => (
            <details className="result-row" key={result.id}>
              <summary>
                <span className={`query-state ${result.status}`} aria-hidden="true" />
                <span className="result-question">{result.question}</span>
                <span className="result-inline-metrics">
                  {Array.from(groupedMetrics(result.metrics).entries()).map(([metric, scores]) => (
                    <span key={metric} title={metric.replaceAll("_", " ")}>
                      {metric === "context_recall"
                        ? "CR"
                        : metric === "faithfulness"
                          ? "F"
                          : metric === "answer_relevance"
                            ? "AR"
                            : "H"}{" "}
                      <b className={metricScoreTone(metric, averageScores(scores))}>
                        {formatPercent(averageScores(scores), 0)}
                      </b>
                    </span>
                  ))}
                </span>
                <span className="result-latency">{formatMs(result.latency_ms)}</span>
                <span className="chevron">
                  <ChevronIcon />
                </span>
              </summary>
              <ResultDetails result={result} />
            </details>
          ))}
        </div>
      ) : (
        <p className="muted-copy results-empty">
          {data?.total ? "No results match the current filters." : "No query results yet."}
        </p>
      )}

      {(data?.total ?? 0) > PAGE_SIZE ? (
        <div className="pagination">
          <button
            className="button secondary small"
            type="button"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            Previous
          </button>
          <span>
            {offset + 1}–{Math.min(offset + PAGE_SIZE, data?.total ?? 0)} of {data?.total}
          </span>
          <button
            className="button secondary small"
            type="button"
            disabled={offset + PAGE_SIZE >= (data?.total ?? 0)}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            Next
          </button>
        </div>
      ) : null}
    </Panel>
  );
}
