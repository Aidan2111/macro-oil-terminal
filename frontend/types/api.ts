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

// ---- Sub-G: live wire shapes (backend Pydantic v2) --------------------
// These mirror backend/models/spread.py + backend/models/inventory.py +
// backend/models/backtest.py exactly. The older `SpreadResponse` /
// `InventoryResponse` / `BacktestResponse` above are scaffold shapes
// kept around for earlier Sub-X code; the charts + ticker consume
// these live shapes.

export type SpreadHistoryPoint = {
  date: string;
  brent: number | null;
  wti: number | null;
  spread: number | null;
  z_score: number | null;
};

export type SpreadLiveResponse = {
  brent: number;
  wti: number;
  spread: number;
  stretch: number | null;
  stretch_band: string;
  as_of: string;
  source: string;
  history: SpreadHistoryPoint[];
};

export type InventoryPoint = {
  date: string;
  commercial_bbls: number | null;
  spr_bbls: number | null;
  cushing_bbls: number | null;
  total_bbls: number | null;
};

export type DepletionForecast = {
  daily_depletion_bbls: number;
  weekly_depletion_bbls: number;
  projected_floor_date: string | null;
  r_squared: number;
  floor_bbls: number;
};

export type InventoryLiveResponse = {
  commercial_bbls: number;
  spr_bbls: number;
  cushing_bbls: number;
  total_bbls: number;
  as_of: string;
  source: string;
  history: InventoryPoint[];
  forecast: DepletionForecast;
};

export type BacktestEquityPoint = {
  Date?: string | null;
  cum_pnl_usd?: number | null;
};

export type BacktestLiveResponse = {
  sharpe: number | null;
  sortino: number | null;
  calmar: number | null;
  var_95?: number | null;
  es_95?: number | null;
  /** Q3 prediction-quality slice — Expected Shortfall at 97.5% confidence
   *  (average loss in the worst 2.5% of trades). Surfaced on the new
   *  `BacktestRiskMetrics` strip. */
  es_975?: number | null;
  max_drawdown: number | null;
  hit_rate: number | null;
  total_pnl_usd: number | null;
  n_trades: number;
  avg_days_held?: number | null;
  avg_pnl_per_bbl?: number | null;
  rolling_12m_sharpe?: number | null;
  equity_curve: BacktestEquityPoint[];
  trades: Array<Record<string, unknown>>;
  params: Record<string, unknown>;
};

export type BacktestRequestBody = {
  entry_z?: number;
  exit_z?: number;
  lookback_days?: number;
  slippage_per_bbl?: number;
  commission_per_trade?: number;
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

// ---- Sub-F: hero / thesis — full execution-decorated shape ------------

/**
 * Canonical stance enum. The backend may emit lower-case in JSON; the
 * frontend normalises at the parse boundary via `lib/api.ts ::
 * normalizeStance()` so consumers can rely on the upper-case form.
 */
export type Stance =
  | "LONG_SPREAD"
  | "SHORT_SPREAD"
  | "FLAT"
  | "STAND_ASIDE";

export type Instrument = {
  tier: 1 | 2 | 3;
  name: string;
  symbol: string | null;
  rationale: string;
  suggested_size_pct: number;
  worst_case_per_unit: string;
};

export type ChecklistItem = {
  key: string;
  prompt: string;
  /** null/None = user must tick; true/false = pre-populated. */
  auto_check: boolean | null;
};

export type ThesisRaw = {
  stance?: Stance | string;
  conviction_0_to_10?: number;
  time_horizon_days?: number;
  thesis_summary?: string;
  plain_english_headline?: string;
  key_drivers?: string[];
  invalidation_risks?: string[];
  catalyst_watchlist?: Array<{ event: string; date: string; expected_impact: string }>;
  data_caveats?: string[];
  position_sizing?: {
    method?: string;
    suggested_pct_of_capital?: number;
    rationale?: string;
  };
  entry?: Record<string, unknown>;
  exit?: Record<string, unknown>;
  reasoning_summary?: string;
  disclaimer_shown?: boolean;
};

/**
 * Serialised `trade_thesis.Thesis` dataclass — matches the `done` event
 * of the SSE stream and the decorated rows the UI renders.
 */
export type Thesis = {
  raw: ThesisRaw;
  generated_at: string;
  source: string;
  model: string | null;
  plain_english_headline: string;
  context_fingerprint: string;
  guardrails_applied: string[];
  mode: string;
  latency_s: number;
  streamed: boolean;
  retried: boolean;
  instruments: Instrument[];
  checklist: ChecklistItem[];
};

/** A row inside `data/trade_theses.jsonl` — the shape `/api/thesis/latest` exposes. */
export type ThesisAuditRecord = {
  timestamp: string;
  source: string;
  model: string | null;
  context_fingerprint: string;
  context: Record<string, unknown> & {
    hours_to_next_eia?: number | null;
    current_z?: number;
    // Q3 prediction-quality slice — surfaced on the hero card via
    // `CointegrationStat`, `RegimeBadges`, and the GARCH `AdvancedToggle`.
    coint_p_value?: number | null;
    coint_verdict?: string | null;
    coint_half_life_days?: number | null;
    coint_hedge_ratio?: number | null;
    regime_term_structure?: "contango" | "backwardation" | "flat" | null;
    regime_vol_bucket?: "low" | "normal" | "high" | "unknown" | null;
    regime_vol_percentile?: number | null;
    regime_realized_vol_20d_pct?: number | null;
    garch_z?: number | null;
    garch_ok?: boolean | null;
    garch_sigma?: number | null;
    garch_persistence?: number | null;
    garch_fallback_reason?: string | null;
  };
  thesis: ThesisRaw;
  guardrails?: string[];
  /** Decorated rows carry these; legacy rows may not. */
  instruments?: Instrument[];
  checklist?: ChecklistItem[];
};

export type ThesisLatestResponse = {
  thesis: ThesisAuditRecord | null;
  empty: boolean;
  /** Q1 data-quality: optional lineage for the headline numeric. */
  lineage?: Lineage;
};

export type ThesisSseDoneEvent = {
  thesis: Thesis;
  applied_guardrails: string[];
  materiality_flat: boolean;
};

export type ThesisSseProgressEvent = {
  stage: string;
  pct: number;
};

export type ThesisSseDeltaEvent = {
  text: string;
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


// ---- Q1 Data-quality slice -------------------------------------------
// Q1-DATA-QUALITY-TYPES

// ---- Geopolitical: Hormuz transit counter ---------------------------

/** One day's tanker transit count through the Strait of Hormuz. */
export type HormuzTransitPoint = {
  date: string; // ISO date "YYYY-MM-DD"
  count: number;
};

/** Response shape for GET /api/geopolitical/hormuz */
export type HormuzTransitResponse = {
  count_24h: number;
  percentile_1y: number;
  trend_30d: HormuzTransitPoint[];
};

// ---- Q1 Data-quality provider names (extended with hormuz) ----------

export type ProviderName =
  | "yfinance"
  | "eia"
  | "cftc"
  | "aisstream"
  | "alpaca_paper"
  | "audit_log"
  | "hormuz";

export type HealthStatus = "green" | "amber" | "red";

export type ProviderHealth = {
  name: ProviderName;
  status: HealthStatus;
  last_good_at: string | null;
  n_obs: number | null;
  latency_ms: number | null;
  freshness_target_hours: number;
  message: string | null;
};

export type DataQualityEnvelope = {
  generated_at: string;
  overall: HealthStatus;
  providers: ProviderHealth[];
};

/**
 * Optional lineage block attached to /api/thesis/latest. Renders as a
 * tooltip on hover over the spread numeric. Backend writes it only
 * when spread_service has at least one successful fetch in memory.
 */
export type Lineage = {
  source: string;
  symbol: string;
  asof: string | null;
  n_obs: number | null;
  latency_ms: number | null;
};
