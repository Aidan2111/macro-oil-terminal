import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { InstrumentTile } from "@/components/hero/InstrumentTile";
import type { Instrument } from "@/types/api";

afterEach(() => cleanup());

const sampleEtfTier: Instrument = {
  tier: 2,
  name: "USO/BNO ETF pair",
  symbol: "USO/BNO",
  rationale: "long USO / short BNO (WTI vs Brent ETF pair)",
  suggested_size_pct: 2.5,
  worst_case_per_unit: "~$X per $1k notional",
};

describe("InstrumentTile", () => {
  it("renders instrument name + symbol + rationale (legs)", () => {
    render(
      <InstrumentTile tier={2} instrument={sampleEtfTier} stance="LONG_SPREAD" />,
    );
    expect(screen.getByText("USO/BNO ETF pair")).toBeInTheDocument();
    // Symbol renders as a standalone text node (exact match).
    expect(screen.getByText("USO/BNO")).toBeInTheDocument();
    expect(
      screen.getByText(/long USO \/ short BNO/i),
    ).toBeInTheDocument();
  });

  it("tags the tier on the container", () => {
    render(
      <InstrumentTile tier={2} instrument={sampleEtfTier} stance="LONG_SPREAD" />,
    );
    const tile = screen.getByTestId("instrument-tile");
    expect(tile).toHaveAttribute("data-tier", "2");
  });

  it("accent bar carries the stance-coloured class", () => {
    render(
      <InstrumentTile tier={2} instrument={sampleEtfTier} stance="LONG_SPREAD" />,
    );
    const accent = screen.getByTestId("instrument-tile-accent");
    // positive semantic token maps to long stance.
    expect(accent.className).toMatch(/positive/);
  });

  it("accent bar maps SHORT_SPREAD to negative semantic token", () => {
    render(
      <InstrumentTile
        tier={3}
        instrument={{ ...sampleEtfTier, tier: 3 }}
        stance="SHORT_SPREAD"
      />,
    );
    const accent = screen.getByTestId("instrument-tile-accent");
    expect(accent.className).toMatch(/negative/);
  });

  it("renders a disabled 'Execute in paper' primary button", () => {
    render(
      <InstrumentTile tier={2} instrument={sampleEtfTier} stance="LONG_SPREAD" />,
    );
    const btn = screen.getByRole("button", { name: /execute in paper/i });
    expect(btn).toBeDisabled();
  });
});
