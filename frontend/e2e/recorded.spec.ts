import { expect, test } from "@playwright/test";

const deadApiUrl = process.env.EVALFORGE_E2E_DEAD_API_URL ?? "http://127.0.0.1:8999";

test.beforeEach(async ({ page }) => {
  // Make the free-tier "asleep" backend deterministic: abort every API call.
  await page.route(`${deadApiUrl}/**`, (route) => route.abort("connectionrefused"));
});

test("falls back to the recorded demo and keeps a permanent banner", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByText(/Contacting the live API|Waking the live API/)).toBeVisible();
  await expect(page.getByText(/Nothing on this screen is a live run/)).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByText("Recorded demo", { exact: true })).toBeVisible();
  await expect(page.locator(".source-badge").first()).toHaveText("Synthetic demo");

  await page.getByRole("link", { name: "Runs", exact: true }).click();
  await expect(
    page
      .getByRole("link", { name: "Synthetic demo - baseline (top-2)", exact: true })
      .first(),
  ).toBeVisible();
  await expect(
    page
      .getByRole("link", { name: "Synthetic demo - candidate (top-6)", exact: true })
      .first(),
  ).toBeVisible();
  await expect(page.getByText(/Nothing on this screen is a live run/)).toBeVisible();

  const baselineHref = await page
    .getByRole("link", { name: "Open Synthetic demo - baseline (top-2)" })
    .getAttribute("href");
  const candidateHref = await page
    .getByRole("link", { name: "Open Synthetic demo - candidate (top-6)" })
    .getAttribute("href");
  expect(baselineHref).toBeTruthy();
  expect(candidateHref).toBeTruthy();

  await page.goto(baselineHref ?? "/runs");
  await expect(
    page.getByRole("heading", { name: "Synthetic demo - baseline (top-2)" }),
  ).toBeVisible();
  await expect(page.getByText("Synthetic demo", { exact: true }).first()).toBeVisible();
  await expect(page.getByText(/Nothing on this screen is a live run/)).toBeVisible();

  const baselineId = baselineHref?.split("/").pop();
  const candidateId = candidateHref?.split("/").pop();
  await page.goto(`/compare?baseline=${baselineId}&candidate=${candidateId}`);
  await expect(page.getByRole("heading", { name: "Compare the evidence." })).toBeVisible();
  await expect(page.locator(".compare-run-card")).toHaveCount(2);
  await expect(page.getByRole("rowheader", { name: "Context recall" })).toBeVisible();

  await page.goto("/runs/new");
  await expect(page.getByText(/Recorded demo\./)).toBeVisible();
  await expect(page.getByRole("button", { name: "Start evaluation" })).toBeDisabled();
});

test("opens the recorded demo immediately from the wake screen", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Use recorded demo now" }).click();

  await expect(page.getByText(/Nothing on this screen is a live run/)).toBeVisible();
  await expect(page.getByText("Recorded demo", { exact: true })).toBeVisible();
});
