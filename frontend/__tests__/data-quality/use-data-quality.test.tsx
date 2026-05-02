import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { DataQualityTile } from "@/components/data-quality/DataQualityTile";
import type { DataQualityEnvelope } from "@/types/api";

function makeEnvelope(overrides: Partial<DataQualityEnvelope> = {}): DataQualityEnvelope {
  const now = new Date().toISOString();
  return {
    generated_at: now,
    overall: "amber",
    providers: [
      { name: "yfinance", status: "green", last_good_at: now, n_obs: 251, latency_ms: 180, freshness_target_hours: 6, message: null },
      { name: "aisstream", status: "amber", last_good_at: now, n_obs: 41, latency_ms: 12, freshness_target_hours: 0.083, message: null },
    ],
    badges: [
      {
        name: "yfinance",
        tier: "green",
        age_label: "2h ago",
        age_seconds: 7200,
        hide_content: false,
        threshold_hours: 6,
      },
      {
        name: "aisstream",
        tier: "amber",
        age_label: "silent 7 min",
        age_seconds: 420,
        hide_content: false,
        threshold_hours: 0.083,
      },
    ],
    stale_providers: ["aisstream"],
    any_red: false,
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

describe("Issue #108 — freshness pill rendering", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("renders the age_label as a pill on each provider cell", async () => {
    stubFetch(makeEnvelope());
    render(<DataQualityTile />);

    await screen.findByTestId("data-quality-tile");

    const yfPill = await screen.findByTestId("data-quality-pill-yfinance");
    expect(yfPill.textContent).toBe("2h ago");

    const aisPill = await screen.findByTestId("data-quality-pill-aisstream");
    expect(aisPill.textContent).toBe("silent 7 min");
  });

  it("uses the badge tier (not raw status) for the pill colour and dot", async () => {
    stubFetch(makeEnvelope());
    render(<DataQualityTile />);

    const aisCell = await screen.findByTestId("data-quality-cell-aisstream");
    // Backend reported status=amber; badge tier should drive the
    // data-tier attribute we render on the cell.
    expect(aisCell.getAttribute("data-tier")).toBe("amber");
  });

  it("falls back to relTime when no badge present (older API)", async () => {
    const env = makeEnvelope();
    delete (env as Record<string, unknown>).badges;
    stubFetch(env);

    render(<DataQualityTile />);
    const yfPill = await screen.findByTestId("data-quality-pill-yfinance");
    // Older API path — pill text is the relTime("2h ago"-ish) format
    // computed from last_good_at. We just assert the pill renders.
    expect(yfPill.textContent).toBeTruthy();
  });

  it("renders a red tier when a badge says hide_content=true", async () => {
    const env = makeEnvelope({
      overall: "red",
      providers: [
        ...makeEnvelope().providers,
        { name: "eia", status: "red", last_good_at: null, n_obs: null, latency_ms: null, freshness_target_hours: 192, message: null },
      ],
      badges: [
        ...(makeEnvelope().badges ?? []),
        {
          name: "eia",
          tier: "red",
          age_label: "never",
          age_seconds: null,
          hide_content: true,
          threshold_hours: 192,
        },
      ],
      any_red: true,
    });
    stubFetch(env);

    render(<DataQualityTile />);
    const eiaCell = await screen.findByTestId("data-quality-cell-eia");
    await waitFor(() => {
      expect(eiaCell.getAttribute("data-tier")).toBe("red");
    });
    const eiaPill = await screen.findByTestId("data-quality-pill-eia");
    expect(eiaPill.textContent).toBe("never");
  });
});
