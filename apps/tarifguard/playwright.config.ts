import { defineConfig, devices } from "@playwright/test";

const CI = !!process.env.CI;

/**
 * Offline E2E: two web servers — the mock serving API (deterministic fixtures) and the console
 * pointed at it (SERVING_BASE_URL). INGEST_BASE_URL is left unset, so the review BFF serves its
 * fixtures and simulates the server-side freeze. No network, no live backend.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: CI,
  retries: CI ? 2 : 0,
  workers: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: "node tests/mock-serving.mjs",
      port: 8799,
      reuseExistingServer: !CI,
      timeout: 30_000,
    },
    {
      command: "npm run dev",
      url: "http://localhost:3000",
      reuseExistingServer: !CI,
      timeout: 120_000,
      env: { SERVING_BASE_URL: "http://localhost:8799" },
    },
  ],
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
