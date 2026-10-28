import { describe, expect, it } from "vitest";

import { loadRecordedDemo, resolveRecorded } from "./recorded";

describe("recorded demo resolver", () => {
  it("marks metadata as a read-only recorded workspace", async () => {
    const meta = await resolveRecorded<{
      demo_mode: boolean;
      write_protected: boolean;
      live_runs: { enabled: boolean; daily_run_cap: number | null };
    }>("/meta");

    expect(meta?.demo_mode).toBe(true);
    expect(meta?.write_protected).toBe(true);
    expect(meta?.live_runs.enabled).toBe(false);
    expect(meta?.live_runs.daily_run_cap).toBeNull();
  });

  it("lists the two seeded runs with pagination", async () => {
    const demo = await loadRecordedDemo();
    const page = await resolveRecorded<{
      items: Array<{ id: string }>;
      total: number;
      limit: number;
      offset: number;
    }>("/runs?limit=1&offset=1");

    expect(demo.runs).toHaveLength(2);
    expect(page?.total).toBe(2);
    expect(page?.items).toHaveLength(1);
    expect(page?.items[0]?.id).toBe(demo.runs[1]?.id);
    expect(page?.limit).toBe(1);
    expect(page?.offset).toBe(1);
  });

  it("uses sensible defaults when query parameters are absent", async () => {
    const demo = await loadRecordedDemo();
    const page = await resolveRecorded<{
      items: unknown[];
      total: number;
      limit: number;
      offset: number;
    }>("/runs");
    const results = await resolveRecorded<{
      items: unknown[];
      limit: number;
      offset: number;
    }>(`/runs/${demo.runs[0]?.id}/results`);

    expect(page?.total).toBe(2);
    expect(page?.items).toHaveLength(2);
    expect(page?.limit).toBe(20);
    expect(page?.offset).toBe(0);
    expect(results?.items).toHaveLength(20);
    expect(results?.offset).toBe(0);
  });

  it("filters runs by status and dataset version", async () => {
    const demo = await loadRecordedDemo();
    const succeeded = await resolveRecorded<{ total: number }>("/runs?status=succeeded");
    const failed = await resolveRecorded<{ total: number }>("/runs?status=failed");
    const versionId = demo.runs[0]?.dataset_version_id;
    const byVersion = await resolveRecorded<{ total: number }>(
      `/runs?dataset_version_id=${versionId}`,
    );

    expect(succeeded?.total).toBe(2);
    expect(failed?.total).toBe(0);
    expect(byVersion?.total).toBe(2);
  });

  it("returns dataset detail and a sliced result page", async () => {
    const demo = await loadRecordedDemo();
    const dataset = await resolveRecorded<{ items: unknown[] }>(
      `/datasets/${demo.datasets[0]?.id}`,
    );
    expect(dataset?.items).toHaveLength(112);

    const run = demo.runs[0];
    const results = await resolveRecorded<{
      items: Array<{ id: string }>;
      total: number;
      limit: number;
      offset: number;
    }>(`/runs/${run?.id}/results?limit=3&offset=2`);
    const full = demo.run_results[run?.id ?? ""];

    expect(results?.total).toBe(112);
    expect(results?.items).toHaveLength(3);
    expect(results?.items[0]?.id).toBe(full?.items[2]?.id);
    expect(results?.offset).toBe(2);
  });

  it("returns a stored comparison for either run order", async () => {
    const demo = await loadRecordedDemo();
    const [baseline, candidate] = demo.runs;
    const forward = await resolveRecorded<{ baseline: { id: string }; rows: unknown[] }>(
      `/runs/compare?baseline_id=${baseline?.id}&candidate_id=${candidate?.id}`,
    );
    const reverse = await resolveRecorded<{ baseline: { id: string }; rows: unknown[] }>(
      `/runs/compare?baseline_id=${candidate?.id}&candidate_id=${baseline?.id}`,
    );

    expect(forward?.baseline.id).toBe(baseline?.id);
    expect(reverse?.baseline.id).toBe(candidate?.id);
    expect(forward?.rows.length).toBeGreaterThan(0);
    expect(reverse?.rows.length).toBe(forward?.rows.length);
  });

  it("returns undefined for records outside the export", async () => {
    await expect(resolveRecorded("/datasets/not-a-real-id")).resolves.toBeUndefined();
    await expect(resolveRecorded("/runs/not-a-real-id")).resolves.toBeUndefined();
    await expect(resolveRecorded("/unknown")).resolves.toBeUndefined();
  });
});
