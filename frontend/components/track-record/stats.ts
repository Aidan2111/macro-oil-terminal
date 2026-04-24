import type { ThesisRow, ThesisStance } from "./types";

/**
 * Threshold for "high-confidence" theses. Matches the 7/10 cut-off
 * used elsewhere in the app (hero card, alerts). Anything below is
 * counted as informational only and skipped for hit-rate / Sharpe
 * stats — we want the reader to judge us on the calls we actually
 * claimed were worth acting on.
 */
export const HIGH_CONFIDENCE_CUTOFF = 7;

export type StanceBucket = {
  total: number;
  hits: number;
  hit_rate: number;
};

export type TrackStats = {
  total_count: number;
  high_confidence_count: number;
  hit_rate: number;
  avg_hold_days: number;
  avg_return: number;
  sharpe: number;
  stance_outcomes: Record<"long" | "short" | "flat", StanceBucket>;
};

function isActioned(stance?: ThesisStance): boolean {
  return stance === "long_spread" || stance === "short_spread";
}

/** Return only the rows we claim to be able to measure. */
export function filterHighConfidenceActioned(rows: ThesisRow[]): ThesisRow[] {
  return rows.filter((r) => {
    const t = r.thesis;
    if (!t) return false;
    if (!isActioned(t.stance)) return false;
    const conv = t.conviction_0_to_10 ?? 0;
    if (conv < HIGH_CONFIDENCE_CUTOFF) return false;
    const outcome = t.outcome;
    // We need *something* to measure — return and hold, at minimum.
    // A thesis with no outcome is still-open and is excluded.
    return outcome != null && outcome.realized_return_pct != null;
  });
}

function mean(xs: number[]): number {
  if (xs.length === 0) return 0;
  let s = 0;
  for (const x of xs) s += x;
  return s / xs.length;
}

function stdev(xs: number[]): number {
  if (xs.length < 2) return 0;
  const m = mean(xs);
  let v = 0;
  for (const x of xs) v += (x - m) ** 2;
  return Math.sqrt(v / (xs.length - 1));
}

function stanceKey(s?: ThesisStance): "long" | "short" | "flat" {
  if (s === "long_spread") return "long";
  if (s === "short_spread") return "short";
  return "flat";
}

/**
 * Roll up hit rate, avg hold, avg realized return, Sharpe, and per-
 * stance hit rates from a list of thesis audit rows.
 *
 * The Sharpe here is the "Sharpe of the signal" — mean realized
 * return divided by stdev. We do not annualise: the reader already
 * sees the avg hold horizon next to it, and this is a signal-
 * quality stat, not a portfolio return stat.
 */
export function computeTrackStats(rows: ThesisRow[]): TrackStats {
  const actionable = filterHighConfidenceActioned(rows);

  const returns = actionable
    .map((r) => r.thesis.outcome?.realized_return_pct)
    .filter((x): x is number => typeof x === "number");
  const holds = actionable
    .map((r) => r.thesis.outcome?.hold_days)
    .filter((x): x is number => typeof x === "number");
  const hits = actionable.filter((r) => r.thesis.outcome?.hit_target === true).length;

  const m = mean(returns);
  const sd = stdev(returns);
  const sharpe = sd > 0 ? m / sd : 0;

  const byStance: Record<"long" | "short" | "flat", StanceBucket> = {
    long: { total: 0, hits: 0, hit_rate: 0 },
    short: { total: 0, hits: 0, hit_rate: 0 },
    flat: { total: 0, hits: 0, hit_rate: 0 },
  };
  // Stance breakdown covers all high-confidence rows (not just
  // actioned — otherwise flat never appears). But hit-rate semantics
  // require an outcome, so we guard on that.
  const highConf = rows.filter(
    (r) =>
      (r.thesis?.conviction_0_to_10 ?? 0) >= HIGH_CONFIDENCE_CUTOFF &&
      r.thesis?.outcome?.realized_return_pct != null,
  );
  for (const r of highConf) {
    const key = stanceKey(r.thesis.stance);
    byStance[key].total++;
    if (r.thesis.outcome?.hit_target) byStance[key].hits++;
  }
  for (const k of ["long", "short", "flat"] as const) {
    const b = byStance[k];
    b.hit_rate = b.total > 0 ? b.hits / b.total : 0;
  }

  return {
    total_count: rows.length,
    high_confidence_count: actionable.length,
    hit_rate: actionable.length > 0 ? hits / actionable.length : 0,
    avg_hold_days: mean(holds),
    avg_return: m,
    sharpe,
    stance_outcomes: byStance,
  };
}

export type EquityPoint = {
  t: string;
  cum_return: number;
};

/**
 * Cumulative compounded return for the high-confidence actioned
 * theses, in chronological (oldest-first) order. Assumes unit
 * capital per trade and simple additive returns — plenty good
 * enough for a demo equity curve and avoids pretending we modelled
 * portfolio rebalancing.
 */
export function computeEquityCurve(rows: ThesisRow[]): EquityPoint[] {
  const actionable = filterHighConfidenceActioned(rows).slice().sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
  );
  let cum = 0;
  const out: EquityPoint[] = [];
  for (const r of actionable) {
    const ret = r.thesis.outcome?.realized_return_pct ?? 0;
    cum += ret;
    out.push({ t: r.timestamp, cum_return: cum });
  }
  return out;
}

/** Per-trade return bucket for the histogram. Returns %-bucket, count pairs. */
export function computeReturnHistogram(
  rows: ThesisRow[],
  bucketPct = 0.01,
): { bucket: number; count: number }[] {
  const returns = filterHighConfidenceActioned(rows)
    .map((r) => r.thesis.outcome?.realized_return_pct)
    .filter((x): x is number => typeof x === "number");
  if (returns.length === 0) return [];
  const buckets = new Map<number, number>();
  for (const r of returns) {
    const b = Math.round(r / bucketPct) * bucketPct;
    // Round to avoid floating-point bucket drift (0.010000000002 etc).
    const key = Math.round(b * 10000) / 10000;
    buckets.set(key, (buckets.get(key) ?? 0) + 1);
  }
  return Array.from(buckets.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([bucket, count]) => ({ bucket, count }));
}
