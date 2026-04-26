import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { DataQualityTile } from "@/components/data-quality/DataQualityTile";
import type { DataQualityEnvelope } from "@/types/api";

function makeEnvelope(overrides: Partial<DataQualityEnvelope> = {}): DataQualityEnvelope {
  const now = new Date().toISOString();
  return {
    generated_at: now,
    overall: "green",
    providers: [
      { name: "yfinance", status: "green", last_good_at: now, n_obs: 251, latency_ms: 180, freshness_target_hours: 6, message: null },
      { name: "eia", status: "green", last_good_at: now, n_obs: 312, latency_ms: 220, freshness_target_hours: 192, message: null },
      { name: "cftc", status: "green", last_good_at: now, n_obs: 156, latency_ms: 140, freshness_target_hours: 192, message: null },
      { name: "aisstream", status: "green", last_good_at: now, n_obs: 41, latency_ms: 12, freshness_target_hours: 0.083, message: null },
      { name: "alpaca_paper", status: "green", last_good_at: now, n_obs: null, latency_ms: 80, freshness_target_hours: 0.25, message: null },
      { name: "audit_log", status: "green", last_good_at: now, n_obs: null, latency_ms: null, freshness_target_hours: 24, message: null },
    ],
    ...overrides,
  };
}

function stubFetch(env: DataQualityEnvelope) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      new Response(JSON.stringify(env), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    ),
  );
}

describe("DataQualityTile", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("renders all six provider cells when status is green", async () => {
    stubFetch(makeEnvelope());
    render(<DataQualityTile />);

    await screen.findByTestId("data-quality-tile");
    for (const name of ["yfinance", "eia", "cftc", "aisstream", "alpaca_paper", "audit_log"] as const) {
      const cell = await screen.findByTestId(`data-quality-cell-${name}`);
      expect(cell.getAttribute("data-status")).toBe("green");
    }
  });

  it("flags amber when a provider degrades", async () => {
    const env = makeEnvelope({ overall: "amber" });
    env.providers[0].status = "amber";
    env.providers[0].message = "yfinance NaN gap > 5 days";
    stubFetch(env);

    render(<DataQualityTile />);
    const cell = await screen.findByTestId("data-quality-cell-yfinance");
    expect(cell.getAttribute("data-status")).toBe("amber");
    const overall = await screen.findByTestId("data-quality-overall");
    expect(overall.textContent).toContain("Degraded");
  });

  it("flags red when a provider is unreachable", async () => {
    const env = makeEnvelope({ overall: "red" });
    env.providers[0].status = "red";
    env.providers[0].last_good_at = null;
    env.providers[0].message = "yfinance rate-limited";
    stubFetch(env);

    render(<DataQualityTile />);
    const cell = await screen.findByTestId("data-quality-cell-yfinance");
    expect(cell.getAttribute("data-status")).toBe("red");
    const overall = await screen.findByTestId("data-quality-overall");
    await waitFor(() => {
      expect(overall.textContent).toContain("Stale");
    });
  });

  it("shows an error message when /api/data-quality is unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("network down");
      }),
    );
    render(<DataQualityTile />);
    const err = await screen.findByTestId("data-quality-error");
    expect(err.textContent).toContain("Data quality:");
  });
});
