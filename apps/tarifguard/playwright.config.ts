import { defineConfig, devices } from "@playwright/test";

const CI = !!process.env.CI;

// Own the ports so `npm test` is hermetic locally too: a dev stack listening on :3000 must
// never be picked up by the smoke (it would serve live records instead of the mock fixtures).
// Ports are env-overridable, and reuse of a pre-existing server is opt-in (PLAYWRIGHT_REUSE=1).
const WEB_PORT = Number(process.env.PLAYWRIGHT_WEB_PORT ?? 3100);
const MOCK_PORT = Number(process.env.PLAYWRIGHT_MOCK_PORT ?? 8799);
const REUSE = process.env.PLAYWRIGHT_REUSE === "1";

/**
 * Offline E2E: two web servers, the mock serving API (deterministic fixtures) and the console
 * pointed at it (SERVING_BASE_URL). INGEST_BASE_URL is left unset, so the review BFF serves its
 * fixtures and simulates the server-side freeze. No network, no live backend. Both servers bind
 * to isolated, env-overridable ports on 127.0.0.1 and do not reuse a pre-existing server unless
 * PLAYWRIGHT_REUSE=1, so the smoke is deterministic in CI and locally alike.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: CI,
  retries: CI ? 2 : 0,
  workers: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: `http://127.0.0.1:${WEB_PORT}`,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: "node tests/mock-serving.mjs",
      port: MOCK_PORT,
      env: { MOCK_PORT: String(MOCK_PORT) },
      reuseExistingServer: REUSE,
      timeout: 30_000,
    },
    {
      command: `npm run dev -- -p ${WEB_PORT} -H 127.0.0.1`,
      url: `http://127.0.0.1:${WEB_PORT}`,
      reuseExistingServer: REUSE,
      timeout: 120_000,
      env: { SERVING_BASE_URL: `http://127.0.0.1:${MOCK_PORT}` },
    },
  ],
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
