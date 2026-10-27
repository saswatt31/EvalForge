import type { RunStatus } from "./types";

const dateFormatter = new Intl.DateTimeFormat("en-US", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "UTC",
});

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return `${dateFormatter.format(date)} UTC`;
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "n/a";
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatScore(value: number | null | undefined): string {
  if (value === null || value === undefined) return "n/a";
  return value.toFixed(3);
}

export function formatDelta(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined) return "n/a";
  return `${value >= 0 ? "+" : ""}${value.toFixed(digits)}`;
}

export function formatMs(value: number | null | undefined): string {
  if (value === null || value === undefined) return "n/a";
  if (value >= 1000) return `${(value / 1000).toFixed(2)} s`;
  return `${value.toFixed(0)} ms`;
}

export function formatNumber(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "n/a";
  return value.toLocaleString("en-US", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function shortId(value: string | null | undefined, length = 8): string {
  if (!value) return "—";
  return value.slice(0, length);
}

export function runProgress(completed: number, failed: number, total: number): number {
  if (total <= 0) return 0;
  return Math.min(100, Math.round(((completed + failed) / total) * 100));
}

export function runDuration(startedAt: string | null, finishedAt: string | null): string {
  if (!startedAt) return "—";
  const start = new Date(startedAt).getTime();
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now();
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return "—";
  const seconds = Math.round((end - start) / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${minutes}m ${remainder}s`;
}

export function isActiveStatus(status: RunStatus): boolean {
  return status === "queued" || status === "running";
}

export function statusLabel(status: RunStatus): string {
  if (status === "partial") return "Partial";
  return status.charAt(0).toUpperCase() + status.slice(1);
}

export function metricLabel(metric: string): string {
  const labels: Record<string, string> = {
    context_recall: "Context recall",
    faithfulness: "Faithfulness",
    answer_relevance: "Answer relevance",
    hallucination_rate: "Hallucination rate",
    success_rate: "Success rate",
    latency_p50_ms: "Latency p50",
    latency_p95_ms: "Latency p95",
    ttft_p50_ms: "TTFT p50",
    ttft_p95_ms: "TTFT p95",
    tokens_per_second: "Output tokens/sec",
  };
  return labels[metric] ?? metric;
}

export function metricUnit(metric: string): "percent" | "ms" | "rate" {
  if (metric === "tokens_per_second") return "rate";
  if (metric.startsWith("latency_") || metric.startsWith("ttft_")) return "ms";
  return "percent";
}

export function scoreTone(value: number | null): "good" | "warn" | "bad" | "neutral" {
  if (value === null) return "neutral";
  if (value >= 0.8) return "good";
  if (value >= 0.55) return "warn";
  return "bad";
}

export function metricScoreTone(
  metric: string,
  value: number | null,
): "good" | "warn" | "bad" | "neutral" {
  if (metric !== "hallucination_rate" || value === null) return scoreTone(value);
  if (value <= 0.2) return "good";
  if (value <= 0.45) return "warn";
  return "bad";
}
