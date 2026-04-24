import type { SpreadLiveResponse } from "@/types/api";

/**
 * Deterministic fixture mimicking GET /api/spread — 90 bars of sine-wave
 * priced Brent/WTI with a wobbling spread and a plausible rolling z.
 */
export function makeSpreadFixture(points = 90): SpreadLiveResponse {
  const history = Array.from({ length: points }, (_, i) => {
    const d = new Date("2026-01-24T00:00:00Z");
    d.setUTCDate(d.getUTCDate() + i);
    const spread = 3 + Math.sin(i / 5) * 1.5;
    const brent = 82 + Math.sin(i / 7);
    const wti = brent - spread;
    return {
      date: d.toISOString().slice(0, 10),
      brent,
      wti,
      spread,
      z_score: Math.sin(i / 11) * 2.5,
    };
  });
  const latest = history[history.length - 1]!;
  return {
    brent: latest.brent ?? 82,
    wti: latest.wti ?? 79,
    spread: latest.spread ?? 3,
    stretch: latest.z_score ?? 0.5,
    stretch_band: "Stretched",
    as_of: latest.date,
    source: "yfinance",
    history,
  };
}
