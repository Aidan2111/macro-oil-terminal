import { expect, test } from "@playwright/test";
import { installApiFixtures } from "./_fixtures";

// @mobile tag — runs under the mobile-chromium project (Pixel 7 viewport).
test.describe("Mobile viewport sanity @mobile", () => {
  test.beforeEach(async ({ page }) => {
    await installApiFixtures(page);
  });

  test("home renders without horizontal scroll on Pixel 7", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("body")).toBeVisible();
    // Document body width must not exceed the viewport — horizontal
    // scroll on mobile is the most common visual regression.
    const overflow = await page.evaluate(() => {
      const body = document.body;
      const html = document.documentElement;
      const docWidth = Math.max(body.scrollWidth, html.scrollWidth);
      const viewWidth = window.innerWidth;
      return { docWidth, viewWidth, overflowing: docWidth > viewWidth + 1 };
    });
    expect(overflow.overflowing).toBe(false);
  });

  test("data-quality grid wraps to fit a narrow mobile column", async ({ page }) => {
    await page.goto("/");
    const tile = page.getByTestId("data-quality-tile");
    await expect(tile).toBeVisible({ timeout: 15_000 });
    // The first cell must be visible and must not be wider than the
    // viewport — confirms the grid responsive class actually fires
    // on a 393-px Pixel viewport.
    const cell = page.getByTestId("data-quality-cell-yfinance");
    const box = await cell.boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      const view = await page.viewportSize();
      expect(box.width).toBeLessThanOrEqual((view?.width ?? 393) + 1);
    }
  });
});
