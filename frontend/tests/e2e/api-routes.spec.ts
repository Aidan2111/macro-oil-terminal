import { expect, test } from "@playwright/test";
import { installApiFixtures } from "./_fixtures";

test.describe("API routes — fixture-pinned shape contracts", () => {
  test.beforeEach(async ({ page }) => {
    await installApiFixtures(page);
  });

  test("/api/spread fixture body matches SpreadResponse shape", async ({ request, page }) => {
    // Trigger the route by visiting the home page so Playwright wires
    // the fixture, then use the `request` context which honours the
    // same routing.
    await page.goto("/");
    const resp = await page.request.get("/api/spread");
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(typeof body.brent).toBe("number");
    expect(typeof body.wti).toBe("number");
    expect(typeof body.spread).toBe("number");
    expect(Array.isArray(body.history)).toBe(true);
  });

  test("/api/calibration fixture exposes underconfident verdict and 87 shadow rows", async ({ page }) => {
    await page.goto("/");
    const resp = await page.request.get("/api/calibration");
    const body = await resp.json();
    expect(body.verdict).toBe("underconfident");
    expect(body.n_total).toBe(87);
    expect(body.sources?.shadow_burn_in).toBe(87);
  });

  test("/api/data-quality fixture has badges + stale_providers + any_red", async ({ page }) => {
    await page.goto("/");
    const resp = await page.request.get("/api/data-quality");
    const body = await resp.json();
    expect(Array.isArray(body.badges)).toBe(true);
    expect(body.badges.length).toBe(7);
    expect(Array.isArray(body.stale_providers)).toBe(true);
    expect(typeof body.any_red).toBe("boolean");
  });

  test("/api/alerts fixture is empty when fleet is healthy", async ({ page }) => {
    await page.goto("/");
    const resp = await page.request.get("/api/alerts");
    const body = await resp.json();
    expect(body.alert_count).toBe(0);
    expect(body.highest_severity).toBe("none");
    expect(Array.isArray(body.alerts)).toBe(true);
  });

  test("404 catch-all fires for unmocked /api/* paths", async ({ page }) => {
    await page.goto("/");
    const resp = await page.request.get("/api/this-route-does-not-exist");
    expect(resp.status()).toBe(404);
    const body = await resp.json();
    expect(body.detail).toBe("fixture-not-defined");
  });
});
