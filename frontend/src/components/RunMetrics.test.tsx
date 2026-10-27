import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { RunMetrics as Metrics } from "@/lib/types";
import { RunMetrics } from "./RunMetrics";

function makeMetrics(overrides: Partial<Metrics> = {}): Metrics {
  return {
    context_recall: { mean: 0.82, judged_queries: 112, total_samples: 112, failed_samples: 0 },
    faithfulness: { mean: 0.88, judged_queries: 112, total_samples: 112, failed_samples: 1 },
    answer_relevance: { mean: 0.79, judged_queries: 112, total_samples: 112, failed_samples: 0 },
    hallucination_rate: {
      mean: 0.12,
      judged_queries: 112,
      total_samples: 112,
      failed_samples: 0,
    },
    latency: {
      p50_ms: 620,
      p95_ms: 850,
      mean_ms: 671,
      ttft_p50_ms: 180,
      ttft_p95_ms: 260,
      measured_ttft_count: 108,
      target_reported_ttft_count: 2,
      demo_ttft_count: 0,
      mean_tokens_per_second: 42.5,
    },
    success_rate: 0.85,
    cache_hits: 12,
    cache_misses: 4,
    ...overrides,
  };
}

describe("RunMetrics", () => {
  it("renders quality, latency, TTFT provenance, and cache data", () => {
    render(<RunMetrics metrics={makeMetrics()} />);

    expect(screen.getByText("Context recall")).toBeInTheDocument();
    expect(screen.getByText("0.820")).toHaveClass("good");
    expect(screen.getByText("85.0% success")).toBeInTheDocument();
    expect(screen.getByText("850 ms")).toBeInTheDocument();
    expect(screen.getByText("42.5")).toBeInTheDocument();
    expect(screen.getByText(/108 measured/)).toHaveTextContent(
      "108 measured · 2 target-reported",
    );
    expect(screen.getByText("Judge cache").parentElement).toHaveTextContent(
      "12 hits · 4 misses",
    );
    expect(screen.queryByText(/Demo timings/)).not.toBeInTheDocument();
  });

  it("treats hallucination as an inverted metric", () => {
    render(
      <RunMetrics
        metrics={makeMetrics({
          hallucination_rate: {
            mean: 0.72,
            judged_queries: 112,
            total_samples: 112,
            failed_samples: 0,
          },
        })}
      />,
    );

    const card = screen.getByText("Hallucination rate").closest(".metric-card");
    expect(card?.querySelector(".metric-number")).toHaveClass("bad");
    expect(card?.querySelector(".metric-number")).not.toHaveClass("good");
  });

  it("labels demo timing as simulated", () => {
    const metrics = makeMetrics();
    metrics.latency = {
      ...metrics.latency,
      measured_ttft_count: 0,
      target_reported_ttft_count: 0,
      demo_ttft_count: 112,
    };

    render(<RunMetrics metrics={metrics} demo />);

    expect(screen.getByText(/112 simulated/)).toBeInTheDocument();
    expect(screen.getByText(/Demo timings are simulated/)).toBeInTheDocument();
  });

  it("shows a clear missing-TTFT state", () => {
    const metrics = makeMetrics();
    metrics.latency = {
      ...metrics.latency,
      ttft_p50_ms: null,
      ttft_p95_ms: null,
      measured_ttft_count: 0,
      target_reported_ttft_count: 0,
      demo_ttft_count: 0,
    };

    render(<RunMetrics metrics={metrics} />);

    expect(screen.getByText(/No TTFT samples were recorded/)).toBeInTheDocument();
  });
});
