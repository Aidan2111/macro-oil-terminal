import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { TrackRecord } from "@/components/track-record/TrackRecord";
import {
  computeTrackStats,
  computeEquityCurve,
} from "@/components/track-record/stats";
import type { ThesisRow } from "@/components/track-record/types";
import thesesFixtureRaw from "@/__tests__/fixtures/theses.json";

const thesesFixture = thesesFixtureRaw as unknown as {
  count: number;
  theses: ThesisRow[];
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// Recharts uses ResizeObserver which jsdom lacks.
class RO {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = RO;

describe("computeTrackStats", () => {
  it("computes hit rate on high-confidence actioned theses only", () => {
    // Fixture has 4 high-confidence (>=7) actioned (non-flat) theses:
    //   a1 (hit), a2 (miss), a4 (hit), a5 (hit) → 3/4 = 0.75
    // a3 is flat (excluded); a6 is low-conviction (excluded).
    const stats = computeTrackStats(thesesFixture.theses);
    expect(stats.hit_rate).toBeCloseTo(0.75, 2);
    expect(stats.high_confidence_count).toBe(4);
  });

  it("computes avg hold across high-confidence actioned theses", () => {
    // holds: 8, 12, 15, 9 → mean 11
    const stats = computeTrackStats(thesesFixture.theses);
    expect(stats.avg_hold_days).toBeCloseTo(11, 1);
  });

  it("computes average realized return", () => {
    // returns: 0.045, -0.015, 0.06, 0.035 → mean 0.03125
    const stats = computeTrackStats(thesesFixture.theses);
    expect(stats.avg_return).toBeCloseTo(0.03125, 4);
  });

  it("Sharpe is ratio of mean to stdev of returns (finite on varied inputs)", () => {
    const stats = computeTrackStats(thesesFixture.theses);
    // stdev > 0 for our mixed set → sharpe must be finite.
    expect(Number.isFinite(stats.sharpe)).toBe(true);
  });

  it("stance outcomes count hits per stance", () => {
    const stats = computeTrackStats(thesesFixture.theses);
    // long: 2 hits (a1, a4) out of 2 high-conf longs → 100%
    // short: 1 hit (a5) out of 2 → 50%
    expect(stats.stance_outcomes.long.hit_rate).toBeCloseTo(1.0, 2);
    expect(stats.stance_outcomes.short.hit_rate).toBeCloseTo(0.5, 2);
  });
});

describe("computeEquityCurve", () => {
  it("cumulates returns oldest-first, assuming unit capital", () => {
    const curve = computeEquityCurve(thesesFixture.theses);
    // Actioned high-conf returns in chronological order: a5 (+0.035), a4 (+0.06), a2 (-0.015), a1 (+0.045)
    // Cumulative: 0.035, 0.095, 0.080, 0.125
    expect(curve).toHaveLength(4);
    expect(curve[0].cum_return).toBeCloseTo(0.035, 3);
    expect(curve[curve.length - 1].cum_return).toBeCloseTo(0.125, 3);
  });
});

describe("TrackRecord component", () => {
  it("fetches /api/thesis/history and renders without crashing", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify(thesesFixture), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<TrackRecord />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.getByTestId("track-record")).toBeInTheDocument(),
    );
    const callArgs = fetchMock.mock.calls[0] as unknown[];
    const url = callArgs[0];
    expect(String(url)).toMatch(/\/api\/thesis\/history\?limit=200/);
    // Stats block renders once data is in.
    await waitFor(() =>
      expect(screen.getByTestId("stat-hit-rate")).toBeInTheDocument(),
    );
  });
});
