import { describe, it, expect, afterEach, vi, beforeEach } from "vitest";
import { render, screen, cleanup, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TradeIdeaHeroClient } from "@/components/hero/TradeIdeaHeroClient";
import type { ThesisAuditRecord, ThesisLatestResponse } from "@/types/api";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function wrap(children: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const SAMPLE_RECORD: ThesisAuditRecord = {
  timestamp: "2026-04-24T09:00:00Z",
  source: "Azure OpenAI: gpt-4o-mini",
  model: "gpt-4o-mini",
  context_fingerprint: "abc123",
  context: {
    current_z: 2.1,
    hours_to_next_eia: 62.5,
    vol_spread_1y_percentile: 50.0,
  },
  thesis: {
    stance: "long_spread",
    conviction_0_to_10: 7,
    time_horizon_days: 14,
    thesis_summary: "Spread is stretched long — mean-reversion setup.",
    plain_english_headline:
      "Brent is trading unusually expensive vs WTI. Bet on the gap closing.",
    key_drivers: ["stretch"],
    invalidation_risks: ["tail risk"],
    catalyst_watchlist: [],
    data_caveats: [],
    position_sizing: { suggested_pct_of_capital: 5 },
  },
  instruments: [
    {
      tier: 1,
      name: "Paper",
      symbol: null,
      rationale: "Track the thesis without capital at risk.",
      suggested_size_pct: 0,
      worst_case_per_unit: "N/A",
    },
    {
      tier: 2,
      name: "USO/BNO ETF pair",
      symbol: "USO/BNO",
      rationale: "long USO / short BNO (WTI vs Brent ETF pair)",
      suggested_size_pct: 2.5,
      worst_case_per_unit: "~$X per $1k notional",
    },
    {
      tier: 3,
      name: "CL=F / BZ=F futures",
      symbol: "CL=F/BZ=F",
      rationale: "long CL=F / short BZ=F (futures calendar pair)",
      suggested_size_pct: 5,
      worst_case_per_unit: "$1000 per contract per $1 move",
    },
  ],
  checklist: [
    { key: "stop_in_place", prompt: "I have a stop at ±2σ.", auto_check: null },
    { key: "vol_clamp_ok", prompt: "Vol below 85th percentile.", auto_check: true },
    { key: "half_life_ack", prompt: "Half-life is ~N days.", auto_check: null },
    { key: "catalyst_clear", prompt: "No EIA within 24h.", auto_check: true },
    {
      key: "no_conflicting_recent_thesis",
      prompt: "No stance flip in recent thesis entries.",
      auto_check: null,
    },
  ],
};

function mockLatest(payload: ThesisLatestResponse) {
  return vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/api/thesis/latest")) {
        return new Response(JSON.stringify(payload), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      }
      if (url.includes("/api/thesis/generate")) {
        // Return an empty event-stream so the SSE loop exits cleanly in tests.
        const stream = new ReadableStream<Uint8Array>({
          start(controller) {
            controller.close();
          },
        });
        return new Response(stream, {
          status: 200,
          headers: { "content-type": "text/event-stream" },
        });
      }
      return new Response("{}", { status: 200 });
    }),
  );
}

describe("TradeIdeaHeroClient", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("renders stance pill, confidence bar, instrument tiles, checklist, and countdown from initialData", async () => {
    mockLatest({ thesis: SAMPLE_RECORD, empty: false });
    render(
      wrap(
        <TradeIdeaHeroClient
          initialData={{ thesis: SAMPLE_RECORD, empty: false }}
        />,
      ),
    );

    // StancePill
    expect(screen.getByTestId("stance-pill")).toBeInTheDocument();
    // ConfidenceBar
    expect(screen.getByTestId("confidence-bar")).toBeInTheDocument();
    // Three instrument tiles
    expect(screen.getAllByTestId("instrument-tile")).toHaveLength(3);
    // Checklist
    expect(screen.getByTestId("pre-trade-checklist")).toBeInTheDocument();
    // Countdown
    expect(screen.getByTestId("catalyst-countdown")).toBeInTheDocument();
    // Headline
    expect(
      screen.getByText(/Brent is trading unusually expensive/i),
    ).toBeInTheDocument();
  });

  it("renders loading skeleton when initialData is undefined and fetch is pending", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise(() => {
            // never resolves — forces loading state
          }),
      ),
    );
    render(wrap(<TradeIdeaHeroClient initialData={undefined} />));
    expect(screen.getByTestId("trade-idea-hero-loading")).toBeInTheDocument();
  });

  it("renders ErrorState on fetch failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("boom", { status: 500 })),
    );
    render(wrap(<TradeIdeaHeroClient initialData={undefined} />));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toBeInTheDocument(),
    );
  });
});
