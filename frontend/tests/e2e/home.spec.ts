import { expect, test } from "@playwright/test";
import { installApiFixtures } from "./_fixtures";

test.describe("Home page", () => {
  test.beforeEach(async ({ page }) => {
    await installApiFixtures(page);
  });

  test("home loads + hero card renders", async ({ page }) => {
    await page.goto("/");
    // Page should render without crashing — body is visible.
    await expect(page.locator("body")).toBeVisible();
    // The data-quality tile renders since the fixture envelope ships.
    await expect(page.getByTestId("data-quality-tile")).toBeVisible({ timeout: 15_000 });
  });

  test("data-quality tile renders all 7 provider cells", async ({ page }) => {
    await page.goto("/");
    for (const name of [
      "yfinance", "eia", "cftc", "aisstream",
      "alpaca_paper", "audit_log", "hormuz",
    ]) {
      await expect(page.getByTestId(`data-quality-cell-${name}`)).toBeVisible({ timeout: 15_000 });
    }
  });

  test("data-quality pills render the age_label from the badges block", async ({ page }) => {
    await page.goto("/");
    const yfPill = page.getByTestId("data-quality-pill-yfinance");
    await expect(yfPill).toBeVisible({ timeout: 15_000 });
    const text = (await yfPill.textContent()) ?? "";
    expect(text.length).toBeGreaterThan(0);
    // Default fixture sets all to green tier — pill colour class is
    // tested in unit tests; here we just lock that the pill renders
    // *something* sensible (e.g. "30s ago", "silent 0s", "warming up").
  });

  test("amber tier on a stale provider shows but doesn't hide content", async ({ page }) => {
    await page.route("**/api/data-quality", async (route) => {
      const now = new Date().toISOString();
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          generated_at: now, overall: "amber",
          providers: [
            { name: "yfinance", status: "amber", last_good_at: now, n_obs: 90, latency_ms: 45, freshness_target_hours: 6, message: null },
          ],
          badges: [
            { name: "yfinance", tier: "amber", age_label: "8h ago", age_seconds: 28800, hide_content: false, threshold_hours: 6 },
          ],
          stale_providers: ["yfinance"],
          any_red: false,
        }),
      });
    });
    await page.goto("/");
    const cell = page.getByTestId("data-quality-cell-yfinance");
    await expect(cell).toBeVisible({ timeout: 15_000 });
    await expect(cell).toHaveAttribute("data-tier", "amber");
    // Cell text should still include "8h ago" — content not hidden.
    await expect(page.getByTestId("data-quality-pill-yfinance")).toContainText("8h ago");
  });

  test("error tile renders when /api/data-quality is unreachable", async ({ page }) => {
    await page.route("**/api/data-quality", async (route) => {
      await route.abort("failed");
    });
    await page.goto("/");
    // Tile component falls back to the error state when the fetch
    // throws. We assert presence of the dedicated testid.
    await expect(page.getByTestId("data-quality-error")).toBeVisible({ timeout: 15_000 });
  });
});
