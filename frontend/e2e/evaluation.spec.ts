import { expect, test } from "@playwright/test";

const apiUrl = process.env.EVALFORGE_E2E_API_URL ?? "http://127.0.0.1:8001";
const token = process.env.EVALFORGE_E2E_TOKEN ?? "evalforge-e2e-token";
const headers = { "X-API-Key": token };

test.describe.configure({ mode: "serial" });

test("imports the sample dataset, runs an evaluation, and compares two runs", async ({
  page,
  request,
}) => {
  await page.goto("/");

  await expect(
    page.getByRole("heading", { name: /Measure what your/ }),
  ).toBeVisible();
  await expect(page.getByText("API connected")).toBeVisible();
  await expect(page.getByText("No benchmark runs yet")).toBeVisible();

  await page.getByRole("link", { name: "Datasets", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "The questions you refuse to guess about." }),
  ).toBeVisible();

  await page.getByRole("button", { name: /Use sample dataset/ }).click();
  await expect(page.getByLabel("Dataset name")).toHaveValue(
    "Reference technical QA · sample",
  );
  await expect(page.getByLabel("JSONL content")).not.toHaveValue("");

  await page.getByRole("button", { name: "Import immutable version" }).click();
  await expect(page).toHaveURL(/\/datasets\/[0-9a-f-]+$/);
  await expect(
    page.getByRole("heading", { name: "Reference technical QA · sample" }),
  ).toBeVisible();
  await expect(page.locator(".dataset-facts").getByText("112", { exact: true })).toBeVisible();

  await page.getByRole("link", { name: "Run this dataset" }).click();
  await expect(page.getByRole("heading", { name: "Run the evidence." })).toBeVisible();
  await expect(page.getByLabel("Dataset version")).toContainText(
    "Reference technical QA · sample",
  );

  await page.getByLabel(/Run name/).fill("Mock baseline");
  await page.getByRole("button", { name: "Start evaluation" }).click();

  await expect(page).toHaveURL(/\/runs\/[0-9a-f-]+$/);
  const baselineId = new URL(page.url()).pathname.split("/").pop();
  expect(baselineId).toBeTruthy();
  await expect(page.getByRole("heading", { name: "Mock baseline" })).toBeVisible();
  await expect(page.locator(".status-badge").first()).toHaveText("Succeeded", {
    timeout: 120_000,
  });
  await expect(page.getByText("100.0% success")).toBeVisible();

  const datasetResponse = await request.get(`${apiUrl}/api/v1/datasets`, { headers });
  expect(datasetResponse.ok()).toBeTruthy();
  const datasets = (await datasetResponse.json()) as Array<{
    latest_version: { id: string };
  }>;
  expect(datasets).toHaveLength(1);

  const candidateResponse = await request.post(`${apiUrl}/api/v1/runs`, {
    headers,
    data: {
      name: "Mock candidate",
      dataset_version_id: datasets[0].latest_version.id,
      target_kind: "reference",
      provider_name: "mock",
      model_name: "mock-extractive-v1",
      pipeline_config: { top_k: 5, prompt_version: "reference-rag-v1" },
      judge_mode: "mock",
      judge_model: "mock-lexical-v1",
      judge_repeats: 1,
      evaluator_config: { judge_provider: "groq" },
      warmup_count: 0,
    },
  });
  expect(candidateResponse.ok()).toBeTruthy();
  const candidate = (await candidateResponse.json()) as { id: string };

  await expect
    .poll(
      async () => {
        const response = await request.get(
          `${apiUrl}/api/v1/runs/${candidate.id}/status`,
          { headers },
        );
        const state = (await response.json()) as { status: string };
        return state.status;
      },
      { timeout: 120_000 },
    )
    .toBe("succeeded");

  await page.goto(`/compare?baseline=${baselineId}&candidate=${candidate.id}`);
  await expect(page.getByRole("heading", { name: "Compare the evidence." })).toBeVisible();
  await expect(page.locator(".compare-run-card")).toHaveCount(2);
  await expect(page.getByRole("rowheader", { name: "Context recall" })).toBeVisible();
  await expect(page.getByRole("rowheader", { name: "Faithfulness" })).toBeVisible();
  await expect(page.getByRole("rowheader", { name: "Hallucination rate" })).toBeVisible();
  await expect(page.getByText("Latency & throughput", { exact: true })).toBeVisible();

  await page.getByRole("link", { name: "Runs", exact: true }).click();
  await expect(page.getByText("Mock baseline", { exact: true })).toBeVisible();
  await expect(page.getByText("Mock candidate", { exact: true })).toBeVisible();
});

test("navigates the dashboard on a narrow viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/runs");

  await page.getByRole("button", { name: "Open navigation" }).click();
  await expect(page.getByRole("link", { name: "Overview", exact: true })).toBeVisible();

  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await expect(page.getByRole("heading", { name: /Measure what your/ })).toBeVisible();
});
