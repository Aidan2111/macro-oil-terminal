import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HormuzTile } from "@/components/geopolitical/HormuzTile";
import type { HormuzTransitResponse } from "@/types/api";

// ---- Fixture factory ---------------------------------------------------

function makeHormuzFixture(overrides: Partial<HormuzTransitResponse> = {}): HormuzTransitResponse {
  const today = new Date();
  const trend_30d = Array.from({ length: 30 }, (_, i) => {
    const d = new Date(today);
    d.setDate(d.getDate() - (29 - i));
    return {
      date: d.toISOString().slice(0, 10),
      count: 10 + i,
    };
  });
  return {
    count_24h: 14,
    percentile_1y: 62.3,
    trend_30d,
    ...overrides,
  };
}

// ---- Fetch stub helper -------------------------------------------------

function stubFetch(fixture: HormuzTransitResponse) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      new Response(JSON.stringify(fixture), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    ),
  );
}

// ---- Wrapper with QueryClientProvider ----------------------------------

function renderWithQuery(ui: React.ReactElement, options: { retry?: number } = {}) {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        retry: options.retry ?? 0,
        retryDelay: 0,
      },
    },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

// ---- Tests ------------------------------------------------------------

describe("HormuzTile", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("renders count and percentile after fetch resolves", async () => {
    const fixture = makeHormuzFixture({ count_24h: 14, percentile_1y: 62.3 });
    stubFetch(fixture);

    renderWithQuery(<HormuzTile />);

    const countEl = await screen.findByTestId("hormuz-count");
    expect(countEl.textContent).toContain("14");

    const pctEl = await screen.findByTestId("hormuz-percentile");
    expect(pctEl).toBeInTheDocument();
    expect(pctEl.textContent).toContain("62");
  });

  it("shows loading skeleton before fetch resolves", () => {
    // Never-resolving fetch — component stays in loading state
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise<Response>(() => {
            // intentionally never resolves
          }),
      ),
    );

    renderWithQuery(<HormuzTile />);

    // ChartShimmer renders with role="img" and aria-label="Chart loading"
    const skeleton = screen.getByRole("img", { name: /chart loading/i });
    expect(skeleton).toBeInTheDocument();
  });

  it("shows error state on fetch failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("network failure");
      }),
    );

    renderWithQuery(<HormuzTile />, { retry: 0 });

    // Error state renders hormuz-tile with an error paragraph
    const tile = await screen.findByTestId("hormuz-tile");
    expect(tile).toBeInTheDocument();
    // hormuz-count should NOT be present in error state
    expect(screen.queryByTestId("hormuz-count")).toBeNull();
  });

  it("renders sparkline with 30 data points after fetch resolves", async () => {
    const fixture = makeHormuzFixture();
    expect(fixture.trend_30d).toHaveLength(30);
    stubFetch(fixture);

    renderWithQuery(<HormuzTile />);

    const sparkline = await screen.findByTestId("hormuz-sparkline");
    expect(sparkline).toBeInTheDocument();
  });
});
