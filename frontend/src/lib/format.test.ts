import { describe, expect, it } from "vitest";

import {
  formatBytes,
  formatDate,
  formatDelta,
  formatMs,
  formatNumber,
  formatPercent,
  formatScore,
  isActiveStatus,
  metricLabel,
  metricScoreTone,
  metricUnit,
  runDuration,
  runProgress,
  scoreTone,
  shortId,
  statusLabel,
} from "./format";

describe("format helpers", () => {
  it("formats nullable scores and deltas consistently", () => {
    expect(formatScore(null)).toBe("n/a");
    expect(formatScore(0.8342)).toBe("0.834");
    expect(formatPercent(0.756)).toBe("75.6%");
    expect(formatPercent(undefined)).toBe("n/a");
    expect(formatDelta(0.125)).toBe("+0.125");
    expect(formatDelta(-0.125)).toBe("-0.125");
    expect(formatDelta(null)).toBe("n/a");
  });

  it("formats latency, numbers, bytes, and identifiers", () => {
    expect(formatMs(84.6)).toBe("85 ms");
    expect(formatMs(1250)).toBe("1.25 s");
    expect(formatMs(null)).toBe("n/a");
    expect(formatNumber(12.345)).toBe("12.3");
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(3 * 1024 * 1024)).toBe("3.0 MB");
    expect(shortId("abcdefghijkl", 8)).toBe("abcdefgh");
    expect(shortId(null)).toBe("—");
  });

  it("formats dates in UTC and rejects invalid values", () => {
    const formatted = formatDate("2026-01-02T03:04:00Z");
    expect(formatted).toContain("2026");
    expect(formatted).toContain("UTC");
    expect(formatDate("not-a-date")).toBe("—");
    expect(formatDate(null)).toBe("—");
  });

  it("calculates bounded run progress and duration", () => {
    expect(runProgress(0, 0, 0)).toBe(0);
    expect(runProgress(1, 1, 3)).toBe(67);
    expect(runProgress(8, 4, 10)).toBe(100);
    expect(runDuration(null, null)).toBe("—");
    expect(runDuration("2026-01-02T03:00:00Z", "2026-01-02T03:00:42Z")).toBe("42s");
    expect(runDuration("2026-01-02T03:00:00Z", "2026-01-02T03:02:05Z")).toBe("2m 5s");
    expect(runDuration("2026-01-02T03:02:00Z", "2026-01-02T03:00:00Z")).toBe("—");
  });

  it("maps statuses, metrics, and score tones", () => {
    expect(isActiveStatus("queued")).toBe(true);
    expect(isActiveStatus("running")).toBe(true);
    expect(isActiveStatus("partial")).toBe(false);
    expect(statusLabel("partial")).toBe("Partial");
    expect(statusLabel("succeeded")).toBe("Succeeded");
    expect(metricLabel("faithfulness")).toBe("Faithfulness");
    expect(metricLabel("custom_metric")).toBe("custom_metric");
    expect(metricUnit("latency_p95_ms")).toBe("ms");
    expect(metricUnit("ttft_p50_ms")).toBe("ms");
    expect(metricUnit("tokens_per_second")).toBe("rate");
    expect(metricUnit("context_recall")).toBe("percent");
    expect(scoreTone(null)).toBe("neutral");
    expect(scoreTone(0.9)).toBe("good");
    expect(scoreTone(0.6)).toBe("warn");
    expect(scoreTone(0.2)).toBe("bad");
    expect(metricScoreTone("faithfulness", 0.9)).toBe("good");
    expect(metricScoreTone("hallucination_rate", 0.1)).toBe("good");
    expect(metricScoreTone("hallucination_rate", 0.3)).toBe("warn");
    expect(metricScoreTone("hallucination_rate", 0.8)).toBe("bad");
    expect(metricScoreTone("hallucination_rate", null)).toBe("neutral");
  });
});
