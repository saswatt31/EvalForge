import { defineConfig } from "@playwright/test";

/**
 * Backend-off suite: runs the dashboard against a port where no API is listening. The app must
 * show the waking state, then open the committed recorded demo with a permanent banner.
 */
const webUrl = process.env.EVALFORGE_E2E_WEB_URL ?? "http://127.0.0.1:3002";
const deadApiUrl = process.env.EVALFORGE_E2E_DEAD_API_URL ?? "http://127.0.0.1:8999";

export default defineConfig({
  testDir: "./e2e",
  testMatch: /recorded\.spec\.ts/,
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 120_000,
  expect: { timeout: 15_000 },
  reporter: process.env.CI
    ? [["github"], ["html", { open: "never" }]]
    : [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: webUrl,
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: [
    {
      command: "npm run dev -- --hostname 127.0.0.1 --port 3002",
      url: webUrl,
      timeout: 120_000,
      reuseExistingServer: false,
      env: {
        ...process.env,
        NEXT_PUBLIC_API_URL: deadApiUrl,
        NEXT_PUBLIC_BACKEND_WAKE_TIMEOUT_MS: "3000",
      },
    },
  ],
});
