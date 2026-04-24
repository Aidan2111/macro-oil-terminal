/**
 * Types for /api/thesis/history rows. Mirrors the audit record in
 * `trade_thesis._append_audit`, plus an optional `outcome` block that
 * the backtest pipeline may write alongside. When `outcome` is
 * absent we treat the thesis as still-open and skip it for stats.
 */

export type ThesisStance = "long_spread" | "short_spread" | "flat";

export type ThesisOutcome = {
  hit_target?: boolean;
  realized_return_pct?: number;
  hold_days?: number;
  closed_at?: string;
};

export type ThesisRaw = {
  stance?: ThesisStance;
  conviction_0_to_10?: number;
  time_horizon_days?: number;
  plain_english_headline?: string;
  thesis_summary?: string;
  entry?: Record<string, unknown>;
  exit?: Record<string, unknown>;
  outcome?: ThesisOutcome;
};

export type ThesisRow = {
  timestamp: string;
  source?: string;
  model?: string;
  context_fingerprint?: string;
  context?: Record<string, unknown>;
  thesis: ThesisRaw;
  guardrails?: unknown[];
};

export type ThesisHistoryResponse = {
  count: number;
  theses: ThesisRow[];
};
