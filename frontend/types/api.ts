/**
 * Hand-written types mirroring the Pydantic response schemas from
 * Sub-A (spread/inventory/CFTC), Sub-B (thesis/backtest), and
 * Sub-C (fleet/positions). Auto-generation via `openapi-typescript`
 * lands in a follow-up — keep these in sync with backend/schemas/*.
 */

export type IsoDateTime = string;

// ---- Sub-A: spread / inventory / CFTC ---------------------------------

export type SpreadPoint = {
  t: IsoDateTime;
  value: number;
};

export type SpreadResponse = {
  symbol: string;
  window: string;
  current: number;
  z_score: number;
  mean: number;
  stdev: number;
  series: SpreadPoint[];
  updated_at: IsoDateTime;
};

export type InventoryRow = {
  week_ending: IsoDateTime;
  crude_stocks_mbbl: number;
  gasoline_stocks_mbbl: number;
  distillate_stocks_mbbl: number;
  wow_delta_mbbl: number;
};

export type InventoryResponse = {
  region: string;
  updated_at: IsoDateTime;
  latest: InventoryRow;
  history: InventoryRow[];
};

// ---- Sub-B: thesis / backtest -----------------------------------------

export type ThesisLeg = {
  instrument: string;
  side: "long" | "short";
  notional_usd: number;
  rationale: string;
};

export type ThesisResponse = {
  id: string;
  generated_at: IsoDateTime;
  title: string;
  summary: string;
  conviction: "low" | "medium" | "high";
  expected_return_bps: number;
  horizon_days: number;
  legs: ThesisLeg[];
  citations: string[];
};

export type BacktestPoint = {
  t: IsoDateTime;
  pnl_usd: number;
  cumulative_pnl_usd: number;
};

export type BacktestResponse = {
  thesis_id: string;
  start: IsoDateTime;
  end: IsoDateTime;
  total_pnl_usd: number;
  sharpe: number;
  max_drawdown_usd: number;
  hit_rate: number;
  series: BacktestPoint[];
};

// ---- Sub-C: fleet / positions -----------------------------------------

export type Vessel = {
  imo: string;
  name: string;
  type: "VLCC" | "Suezmax" | "Aframax" | "LR2" | "LR1" | "MR" | "other";
  lat: number;
  lon: number;
  speed_kn: number;
  heading_deg: number;
  draught_m: number;
  last_seen: IsoDateTime;
};

export type FleetSnapshot = {
  region: string;
  captured_at: IsoDateTime;
  vessel_count: number;
  vessels: Vessel[];
};

export type Position = {
  id: string;
  instrument: string;
  side: "long" | "short";
  quantity: number;
  avg_price: number;
  mark_price: number;
  unrealised_pnl_usd: number;
  opened_at: IsoDateTime;
};

export type Account = {
  id: string;
  name: string;
  base_currency: string;
  equity_usd: number;
  cash_usd: number;
  margin_used_usd: number;
  positions: Position[];
};

// ---- Shared error envelope --------------------------------------------

export type ApiErrorPayload = {
  detail: string;
  code?: string;
};

export type BuildInfo = {
  sha: string;
  sha_short?: string | null;
  time: string;
  region: string;
};
