/**
 * Playwright config — issue #132
 *
 * Strategy: spin up the production-built Next.js export against a
 * fixture-pinned mode of the FastAPI backend (NEXT_PUBLIC_USE_FIXTURES=1
 * routes the frontend at /api/*/fixture so the e2e suite is hermetic).
 *
 * On CI we run chromium only to keep wall-clock under 5 minutes;
 * webkit + firefox are local-only opt-ins.
 */

import { defineConfig, devices } from "@playwright/test";

const PORT = process.env.PLAYWRIGHT_PORT
  ? Number(process.env.PLAYWRIGHT_PORT)
  : 3030;
const BASE_URL = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI
    ? [["github"], ["html", { open: "never" }]]
    : [["list"]],
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    // The frontend assumes a NEXT_PUBLIC_API_BASE — let it default to
    // the same origin so the fixture routes resolve through Next's
    // rewrites in dev / served files in prod.
  },
  webServer: {
    command: `npm run dev -- --port ${PORT}`,
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      // Point the frontend at itself so all /api/* requests stay
      // in-process — tests/e2e/_fixtures.ts uses page.route() to
      // intercept and return canned bodies hermetically.
      NEXT_PUBLIC_API_BASE: BASE_URL,
    },
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    // Mobile viewport sanity — runs only on the mobile-tagged specs.
    {
      name: "mobile-chromium",
      use: { ...devices["Pixel 7"] },
      grep: /@mobile/,
    },
  ],
});
