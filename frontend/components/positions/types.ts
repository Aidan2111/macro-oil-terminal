/**
 * Types for /api/positions and /api/positions/account, mirroring the
 * projections in `backend/services/alpaca_service.py`. Hand-written
 * for now; auto-gen from OpenAPI lands in a follow-up.
 *
 * Secrets never cross this boundary — the backend whitelists every
 * field before it hits the wire.
 */

export type PaperPosition = {
  symbol: string;
  qty: number;
  avg_entry: number;
  current_px: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  /**
   * Optional mapping from a thesis row (by `context_fingerprint` or an
   * explicit `thesis_id` field in the JSONL). The backend may start
   * emitting this in a later wave; the UI already reads it so the row
   * renders a linked thesis id when available.
   */
  thesis_id?: string | null;
};

export type PaperAccount = {
  buying_power: number;
  cash: number;
  equity: number;
  portfolio_value: number;
};

export type PositionsListResponse = {
  positions: PaperPosition[];
};

/**
 * Payload for the `trade_update` SSE event emitted by
 * `/api/positions/stream`. The backend wraps the Alpaca TradeUpdate
 * through `alpaca_service.map_order`, which gives us the order shape
 * plus any live-px fields the server chooses to include.
 */
export type TradeUpdatePayload = {
  event: string;
  order: {
    id: string;
    status: string;
    symbol: string;
    qty: number;
    side: string;
    current_px?: number;
    unrealized_pnl?: number;
    unrealized_pnl_pct?: number;
  } | null;
};

export type ExecuteOrderRequest = {
  symbol: string;
  qty: number;
  side: "buy" | "sell";
  type: "market" | "limit";
  time_in_force: "day" | "gtc" | "ioc" | "fok";
  limit_price?: number | null;
};
