/**
 * Hermetic API fixtures for the Playwright e2e suite (issue #132).
 *
 * Every spec calls `installApiFixtures(page)` in beforeEach so the
 * frontend's /api/** calls are intercepted and answered from canned
 * bodies. No live backend required, no flaky network, no token cost.
 *
 * Specs that need a different body for a single endpoint can override
 * with `page.route('**/api/whatever', …)` AFTER installApiFixtures —
 * Playwright's later route handlers take precedence.
 */

import type { Page, Route } from "@playwright/test";

const NOW = new Date().toISOString();
const ISO_24H_AGO = new Date(Date.now() - 86_400_000).toISOString();

function json(body: unknown) {
  return {
    contentType: "application/json",
    body: JSON.stringify(body),
  };
}

const FIXTURES: Record<string, () => unknown> = {
  "/api/spread": () => ({
    brent: 76.5,
    wti: 71.4,
    spread: 5.1,
    stretch: 0.8,
    stretch_band: "Normal",
    as_of: NOW,
    source: "fixture",
    history: Array.from({ length: 30 }, (_, i) => ({
      date: new Date(Date.now() - (30 - i) * 86_400_000).toISOString().slice(0, 10),
      brent: 75 + Math.sin(i / 4) * 2,
      wti: 70 + Math.sin(i / 4) * 1.7,
      spread: 5 + Math.sin(i / 4) * 0.3,
      z_score: Math.sin(i / 4) * 0.5,
    })),
    corroboration: {
      yfinance: { brent: 76.5, wti: 71.4 },
      fred: { brent: 76.4, wti: 71.5 },
      twelve_data: { brent: null, wti: null },
      max_relative_delta: 0.0014,
    },
  }),
  "/api/inventory": () => ({
    commercial_bbls: 460_000_000,
    spr_bbls: 396_000_000,
    cushing_bbls: 28_000_000,
    total_bbls: 884_000_000,
    as_of: NOW,
    source: "fixture",
    history: [],
  }),
  "/api/cftc": () => ({
    mm_net: 99_000,
    commercial_net: -220_000,
    mm_zscore_3y: -0.12,
    as_of: NOW,
    market: "WTI-PHYSICAL fixture",
    source_url: "fixture://",
    history: [],
  }),
  "/api/data-quality": () => ({
    generated_at: NOW,
    overall: "green",
    providers: [
      {
        name: "yfinance", status: "green", last_good_at: NOW,
        n_obs: 90, latency_ms: 45, freshness_target_hours: 6, message: null,
      },
      {
        name: "eia", status: "green", last_good_at: NOW,
        n_obs: 100, latency_ms: 12, freshness_target_hours: 192, message: null,
      },
      {
        name: "cftc", status: "green", last_good_at: NOW,
        n_obs: 120, latency_ms: 8, freshness_target_hours: 192, message: null,
      },
      {
        name: "aisstream", status: "green", last_good_at: NOW,
        n_obs: 800, latency_ms: 0, freshness_target_hours: 0.083, message: null,
      },
      {
        name: "alpaca_paper", status: "green", last_good_at: NOW,
        n_obs: null, latency_ms: 70, freshness_target_hours: 0.25, message: null,
      },
      {
        name: "audit_log", status: "green", last_good_at: NOW,
        n_obs: 12, latency_ms: null, freshness_target_hours: 24, message: null,
      },
      {
        name: "hormuz", status: "green", last_good_at: NOW,
        n_obs: 30, latency_ms: 5, freshness_target_hours: 1, message: null,
      },
    ],
    badges: [
      { name: "yfinance", tier: "green", age_label: "30s ago", age_seconds: 30, hide_content: false, threshold_hours: 6 },
      { name: "eia", tier: "green", age_label: "30s ago", age_seconds: 30, hide_content: false, threshold_hours: 192 },
      { name: "cftc", tier: "green", age_label: "30s ago", age_seconds: 30, hide_content: false, threshold_hours: 192 },
      { name: "aisstream", tier: "green", age_label: "silent 0s", age_seconds: 0, hide_content: false, threshold_hours: 0.083 },
      { name: "alpaca_paper", tier: "green", age_label: "silent 0s", age_seconds: 0, hide_content: false, threshold_hours: 0.25 },
      { name: "audit_log", tier: "green", age_label: "30s ago", age_seconds: 30, hide_content: false, threshold_hours: 24 },
      { name: "hormuz", tier: "green", age_label: "silent 0s", age_seconds: 0, hide_content: false, threshold_hours: 1 },
    ],
    stale_providers: [],
    any_red: false,
  }),
  "/api/alerts": () => ({
    checked_at: NOW,
    alert_count: 0,
    highest_severity: "none",
    alerts: [],
  }),
  "/api/calibration": () => ({
    n_total: 87,
    brier_score: 0.288,
    mean_signed_error: -0.355,
    verdict: "underconfident",
    buckets: [
      { label: "0-25%", lo: 0, hi: 0.25, midpoint: 0.125, n: 0, hits: 0, hit_rate: 0 },
      { label: "25-50%", lo: 0.25, hi: 0.5, midpoint: 0.375, n: 46, hits: 40, hit_rate: 0.87 },
      { label: "50-75%", lo: 0.5, hi: 0.75, midpoint: 0.625, n: 40, hits: 34, hit_rate: 0.85 },
      { label: "75-100%", lo: 0.75, hi: 1.001, midpoint: 0.875, n: 1, hits: 0, hit_rate: 0 },
    ],
    sources: { live_outcome_closed: 0, shadow_burn_in: 87, shadow_included: true },
  }),
  "/api/thesis/latest": () => ({
    thesis: {
      stance: "short_spread",
      conviction_0_to_10: 6,
      time_horizon_days: 14,
      thesis_summary: "Spread looks stretched; mean-reversion play.",
      key_drivers: ["Z = +1.8", "no major catalyst in next 24h"],
      invalidation_risks: ["sustained Brent rally on supply shock"],
      reasoning_summary: "Fixture body for e2e.",
      plain_english_headline: "Brent–WTI spread stretched — fade it.",
      instruments: [
        { symbol: "CL=F", side: "long", weight: 1 },
        { symbol: "BZ=F", side: "short", weight: 1 },
        { symbol: "USO", side: "neutral", weight: 0 },
      ],
      checklist: [
        { key: "stop_in_place", prompt: "Stop set at ±2σ.", auto_check: null },
        { key: "vol_clamp_ok", prompt: "Vol < 85th percentile.", auto_check: true },
        { key: "catalyst_clear", prompt: "≥ 24h to next EIA.", auto_check: true },
        { key: "size_within_limit", prompt: "Size ≤ 1% of book.", auto_check: null },
        { key: "thesis_understood", prompt: "Read the thesis.", auto_check: null },
      ],
    },
    generated_at: NOW,
    source: "fixture",
    model: "fixture",
    mode: "fast",
    latency_s: 0.1,
  }),
  "/api/thesis/history": () => [],
  "/api/positions/account": () => ({
    cash: 250_000,
    equity: 250_000,
    buying_power: 500_000,
    positions: [],
    source: "fixture",
    as_of: NOW,
  }),
  "/api/build-info": () => ({
    sha: "fixture",
    sha_short: "fixture",
    build_time: NOW,
    branch: "main",
  }),
};

/**
 * Wire all canned API fixtures onto a Playwright page. Call from a
 * `beforeEach` hook in each spec.
 */
export async function installApiFixtures(page: Page): Promise<void> {
  for (const [path, builder] of Object.entries(FIXTURES)) {
    await page.route(`**${path}`, async (route: Route) => {
      await route.fulfill(json(builder()));
    });
  }
  // Catch-all for any /api/* not explicitly mocked — return 404 with
  // a tagged body so the spec can debug fast.
  await page.route("**/api/**", async (route: Route) => {
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: "fixture-not-defined", url: route.request().url() }),
    });
  });
}
