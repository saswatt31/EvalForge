import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api";
import {
  EmptyState,
  ErrorNotice,
  LoadingBlock,
  MetricCard,
  ScoreValue,
  SourceBadge,
  StatusBadge,
} from "./ui";

describe("shared UI", () => {
  it("renders status and source labels", () => {
    const { container } = render(
      <div>
        <StatusBadge status="partial" />
        <SourceBadge source="demo" />
        <SourceBadge source="ci" />
        <SourceBadge source="dashboard" />
      </div>,
    );

    expect(screen.getByText("Partial")).toHaveClass("status-badge", "status-partial");
    expect(screen.getByText("Synthetic demo")).toHaveClass("source-demo");
    expect(screen.getByText("GitHub Action")).toBeInTheDocument();
    expect(screen.queryByText("Dashboard")).not.toBeInTheDocument();
    expect(container.querySelectorAll(".status-badge")).toHaveLength(1);
  });

  it("renders score placeholders with the right tone", () => {
    const { container } = render(
      <div>
        <ScoreValue value={null} />
        <ScoreValue value={0.91} />
        <ScoreValue value={0.61} scale="percent" />
      </div>,
    );

    expect(screen.getByText("n/a")).toHaveClass("neutral");
    expect(screen.getByText("0.910")).toHaveClass("good");
    expect(screen.getByText("61.0%")).toHaveClass("warn");
    expect(container.querySelector(".metric-value.bad")).toBeNull();
  });

  it("renders a metric card with hint content", () => {
    render(
      <MetricCard label="Faithfulness" value="0.842" hint="112 queries" tone="good">
        <div data-testid="metric-extra" />
      </MetricCard>,
    );

    expect(screen.getByText("Faithfulness")).toBeInTheDocument();
    expect(screen.getByText("0.842")).toHaveClass("metric-number", "good");
    expect(screen.getByText("112 queries")).toBeInTheDocument();
    expect(screen.getByTestId("metric-extra")).toBeInTheDocument();
  });

  it("renders empty and loading states", () => {
    render(
      <div>
        <EmptyState title="No runs yet" description="Start an evaluation." />
        <LoadingBlock label="Loading datasets" />
      </div>,
    );

    expect(screen.getByRole("heading", { name: "No runs yet" })).toBeInTheDocument();
    expect(screen.getByText("Start an evaluation.")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Loading datasets…");
  });

  it("shows API issues and authentication guidance", () => {
    const error = new ApiError(401, "Missing write token", undefined, [
      { field: "header", message: "X-API-Key is required" },
    ]);

    render(<ErrorNotice error={error} title="Could not create run" />);

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("Could not create run")).toBeInTheDocument();
    expect(screen.getByText("Missing write token")).toBeInTheDocument();
    expect(screen.getByText("X-API-Key is required")).toBeInTheDocument();
    expect(screen.getByText(/Add the write API token/)).toBeInTheDocument();
  });

  it("explains read-only demo failures", () => {
    render(<ErrorNotice error={new ApiError(403, "Demo mode is read-only")} />);

    expect(screen.getByText("Demo mode is read-only")).toBeInTheDocument();
    expect(screen.getByText("This deployment is a read-only demo.")).toBeInTheDocument();
  });
});
