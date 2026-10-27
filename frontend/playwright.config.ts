import { defineConfig } from "@playwright/test";

const apiUrl = process.env.EVALFORGE_E2E_API_URL ?? "http://127.0.0.1:8001";
const webUrl = process.env.EVALFORGE_E2E_WEB_URL ?? "http://127.0.0.1:3001";
const token = process.env.EVALFORGE_E2E_TOKEN ?? "evalforge-e2e-token";

export default defineConfig({
  testDir: "./e2e",
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
    extraHTTPHeaders: { "X-API-Key": token },
  },
  webServer: [
    {
      command: "node ./e2e/start-backend.mjs",
      url: `${apiUrl}/api/v1/health`,
      timeout: 120_000,
      reuseExistingServer: false,
      env: {
        ...process.env,
        EVALFORGE_E2E_API_PORT: new URL(apiUrl).port,
        EVALFORGE_E2E_TOKEN: token,
      },
    },
    {
      command: "npm run dev -- --hostname 127.0.0.1 --port 3001",
      url: webUrl,
      timeout: 120_000,
      reuseExistingServer: false,
      env: {
        ...process.env,
        NEXT_PUBLIC_API_URL: apiUrl,
      },
    },
  ],
});
