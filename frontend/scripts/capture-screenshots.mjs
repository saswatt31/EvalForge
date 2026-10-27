import { mkdir } from "node:fs/promises";
import path from "node:path";

import { chromium } from "@playwright/test";

const webUrl = process.env.EVALFORGE_WEB_URL ?? "http://localhost:3000";
const apiUrl = process.env.EVALFORGE_API_URL ?? "http://127.0.0.1:8000";
const output = path.resolve(process.cwd(), "../docs/screenshots");

await mkdir(output, { recursive: true });

const runsResponse = await fetch(`${apiUrl}/api/v1/runs?limit=100`);
if (!runsResponse.ok) throw new Error(`Could not load runs (${runsResponse.status})`);
const runs = (await runsResponse.json()).items.filter(
  (run) => run.status === "succeeded" || run.status === "partial",
);
const baseline = runs.find((run) => run.name === "Hybrid retriever baseline") ?? runs[0];
const candidate =
  runs.find((run) => run.name === "Narrow retriever candidate") ??
  runs.find((run) => run.id !== baseline?.id);

const datasetsResponse = await fetch(`${apiUrl}/api/v1/datasets`);
if (!datasetsResponse.ok) throw new Error(`Could not load datasets (${datasetsResponse.status})`);
const datasets = await datasetsResponse.json();
if (!baseline || !candidate || !datasets.length) {
  throw new Error("Seed the API with at least two completed runs and one dataset first.");
}

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  colorScheme: "dark",
  locale: "en-US",
});
const page = await context.newPage();

async function capture(pathname, filename, ready) {
  await page.goto(`${webUrl}${pathname}`, { waitUntil: "networkidle" });
  await ready();
  await page.screenshot({ path: path.join(output, filename), fullPage: true });
  console.log(`captured ${filename}`);
}

await capture("/", "overview.png", async () => {
  await page.locator(".stat-card").first().waitFor();
  await page.locator(".recent-runs .data-table tbody tr").first().waitFor();
});

await capture("/runs", "runs.png", async () => {
  await page.locator(".data-table tbody tr").first().waitFor();
});

await capture(`/runs/${baseline.id}`, "run-detail.png", async () => {
  await page.locator(".status-badge", { hasText: "Succeeded" }).waitFor();
  await page.locator(".metric-card").first().waitFor();
  await page.locator(".result-row").first().waitFor();
});

await capture(
  `/compare?baseline=${baseline.id}&candidate=${candidate.id}`,
  "compare.png",
  async () => {
    await page.locator(".compare-run-card").first().waitFor();
    await page.locator(".compare-table tbody tr").first().waitFor();
  },
);

await capture("/datasets", "datasets.png", async () => {
  await page.locator(".dataset-card").first().waitFor();
});

const dataset = datasets.find((item) => item.name === "Smoke sample dataset") ?? datasets[0];
await capture(`/datasets/${dataset.id}`, "dataset-detail.png", async () => {
  await page.locator(".dataset-item").first().waitFor();
});

await capture("/runs/new", "new-run.png", async () => {
  await page.locator(".run-form").waitFor();
});

await page.setViewportSize({ width: 390, height: 844 });
await capture("/", "overview-mobile.png", async () => {
  await page.locator(".stat-card").first().waitFor();
});
await page.screenshot({
  path: path.join(output, "overview-mobile.png"),
  fullPage: false,
});

await browser.close();
