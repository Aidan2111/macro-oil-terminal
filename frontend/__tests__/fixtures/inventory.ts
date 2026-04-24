import type { InventoryLiveResponse } from "@/types/api";

/**
 * Deterministic fixture mimicking GET /api/inventory — two years of
 * weekly bars with a gentle downward drift.
 */
export function makeInventoryFixture(weeks = 104): InventoryLiveResponse {
  const start = new Date("2024-04-24T00:00:00Z");
  const history = Array.from({ length: weeks }, (_, i) => {
    const d = new Date(start);
    d.setUTCDate(d.getUTCDate() + i * 7);
    const commercial = 430_000_000 - i * 250_000 + Math.sin(i / 6) * 3_000_000;
    const spr = 370_000_000 + Math.cos(i / 9) * 1_000_000;
    const cushing = 45_000_000 + Math.sin(i / 4) * 4_000_000;
    return {
      date: d.toISOString().slice(0, 10),
      commercial_bbls: commercial,
      spr_bbls: spr,
      cushing_bbls: cushing,
      total_bbls: commercial + spr,
    };
  });
  const latest = history[history.length - 1]!;
  return {
    commercial_bbls: latest.commercial_bbls ?? 400_000_000,
    spr_bbls: latest.spr_bbls ?? 370_000_000,
    cushing_bbls: latest.cushing_bbls ?? 45_000_000,
    total_bbls: latest.total_bbls ?? 770_000_000,
    as_of: latest.date,
    source: "EIA",
    history,
    forecast: {
      daily_depletion_bbls: -36_000,
      weekly_depletion_bbls: -252_000,
      projected_floor_date: "2026-11-15",
      r_squared: 0.72,
      floor_bbls: 360_000_000,
    },
  };
}
