"use client";

import * as React from "react";
import { API_BASE } from "@/lib/api";
import { EmptyState } from "@/components/common/EmptyState";
import { Button } from "@/components/ui/button";
import type {
  PaperAccount,
  PaperPosition,
  TradeUpdatePayload,
  ExecuteOrderRequest,
} from "./types";

type Props = {
  initialPositions: PaperPosition[];
  initialAccount: PaperAccount | null;
};

type State = {
  positions: PaperPosition[];
  account: PaperAccount | null;
  closing: Record<string, boolean>;
  lastError: string | null;
};

type Action =
  | { type: "trade_update"; payload: TradeUpdatePayload }
  | { type: "close_start"; symbol: string }
  | { type: "close_done"; symbol: string }
  | { type: "close_fail"; symbol: string; message: string };

/**
 * Merge a live trade-update into the in-memory positions list.
 *
 * The backend's SSE stream wraps the Alpaca TradeUpdate websocket and
 * emits whatever fields it chose to include from the mapped order.
 * We only touch the subset we know about (current_px / P&L) and leave
 * avg_entry / qty alone unless the server sent a new value.
 */
function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "trade_update": {
      const order = action.payload.order;
      if (!order || !order.symbol) return state;
      const idx = state.positions.findIndex((p) => p.symbol === order.symbol);
      if (idx === -1) return state;
      const cur = state.positions[idx];
      const next: PaperPosition = {
        ...cur,
        current_px: order.current_px ?? cur.current_px,
        unrealized_pnl: order.unrealized_pnl ?? cur.unrealized_pnl,
        unrealized_pnl_pct:
          order.unrealized_pnl_pct ?? cur.unrealized_pnl_pct,
      };
      const positions = state.positions.slice();
      positions[idx] = next;
      return { ...state, positions };
    }
    case "close_start":
      return {
        ...state,
        closing: { ...state.closing, [action.symbol]: true },
        lastError: null,
      };
    case "close_done": {
      const closing = { ...state.closing };
      delete closing[action.symbol];
      return { ...state, closing };
    }
    case "close_fail": {
      const closing = { ...state.closing };
      delete closing[action.symbol];
      return { ...state, closing, lastError: action.message };
    }
    default:
      return state;
  }
}

function formatUsd(n: number): string {
  return n.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  });
}

function formatNum(n: number, digits = 2): string {
  return n.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function formatPct(n: number): string {
  // Backend sends Alpaca's fractional pct (e.g. 0.025 = 2.5%).
  return `${(n * 100).toFixed(2)}%`;
}

/**
 * Client body of the Positions panel.
 *
 *   - Reads initial snapshot from the server component.
 *   - Subscribes to `/api/positions/stream` for live trade updates.
 *   - Quick-close POSTs the opposing side to `/api/positions/execute`.
 *
 * The "Paper account" badge is non-removable — a safety signal so the
 * user can never confuse this demo panel with a live account. The
 * server-side handler additionally refuses to execute unless
 * `ALPACA_PAPER=true`; the UI cannot override that gate.
 */
export function PositionsView({ initialPositions, initialAccount }: Props) {
  const [state, dispatch] = React.useReducer(reducer, {
    positions: initialPositions,
    account: initialAccount,
    closing: {},
    lastError: null,
  });

  // SSE live updates — open on mount, close on unmount. Guarded so
  // SSR passes never try to construct an EventSource.
  React.useEffect(() => {
    if (typeof window === "undefined" || typeof EventSource === "undefined") {
      return;
    }
    const url = `${API_BASE}/api/positions/stream`;
    const es = new EventSource(url);
    const onTradeUpdate = (evt: MessageEvent) => {
      try {
        const parsed = JSON.parse(evt.data) as TradeUpdatePayload;
        dispatch({ type: "trade_update", payload: parsed });
      } catch {
        // Ignore malformed payloads — never bubble to the user.
      }
    };
    es.addEventListener("trade_update", onTradeUpdate as EventListener);
    return () => {
      es.removeEventListener("trade_update", onTradeUpdate as EventListener);
      es.close();
    };
  }, []);

  const onClose = React.useCallback(
    async (pos: PaperPosition) => {
      dispatch({ type: "close_start", symbol: pos.symbol });
      const opposing: ExecuteOrderRequest = {
        symbol: pos.symbol,
        qty: Math.abs(pos.qty),
        side: pos.qty > 0 ? "sell" : "buy",
        type: "market",
        time_in_force: "day",
      };
      try {
        const res = await fetch(`${API_BASE}/api/positions/execute`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
          },
          body: JSON.stringify(opposing),
        });
        if (!res.ok) {
          const text = await res.text().catch(() => "");
          dispatch({
            type: "close_fail",
            symbol: pos.symbol,
            message: text || `Close failed (${res.status})`,
          });
          return;
        }
        dispatch({ type: "close_done", symbol: pos.symbol });
      } catch (err) {
        dispatch({
          type: "close_fail",
          symbol: pos.symbol,
          message: String(err),
        });
      }
    },
    [],
  );

  return (
    <div data-testid="positions-panel" className="space-y-4">
      <header className="flex items-center justify-between gap-3">
        <div className="text-sm text-text-secondary">
          Live paper-trading account. Closes fire a market order in the
          opposite direction.
        </div>
        <span
          data-testid="paper-badge"
          className="rounded-btn border border-amber-500/50 bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-300"
          title="All orders placed here are paper (simulated). ALPACA_PAPER=true is enforced server-side."
        >
          Paper account
        </span>
      </header>

      <AccountSummary account={state.account} />

      {state.positions.length === 0 ? (
        <EmptyState
          variant="barrel"
          title="No open paper positions."
          message="Place a trade from any Trade Idea."
        />
      ) : (
        <PositionsTable
          positions={state.positions}
          closing={state.closing}
          onClose={onClose}
        />
      )}

      {state.lastError ? (
        <div
          role="alert"
          className="rounded-btn border border-destructive/50 bg-destructive/10 px-3 py-2 text-xs text-destructive"
        >
          {state.lastError}
        </div>
      ) : null}
    </div>
  );
}

function AccountSummary({ account }: { account: PaperAccount | null }) {
  const bp = account?.buying_power ?? 0;
  const eq = account?.equity ?? 0;
  // Day P&L is not on the account projection today — show equity −
  // portfolio_value as a best-effort proxy, or 0 when they match.
  const dayPnl = account ? account.equity - account.portfolio_value : 0;
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      <SummaryCell
        label="Buying power"
        value={formatUsd(bp)}
        testid="summary-buying-power"
      />
      <SummaryCell
        label="Equity"
        value={formatUsd(eq)}
        testid="summary-equity"
      />
      <SummaryCell
        label="Day P&L"
        value={formatUsd(dayPnl)}
        tone={dayPnl >= 0 ? "pos" : "neg"}
        testid="summary-day-pnl"
      />
    </div>
  );
}

function SummaryCell({
  label,
  value,
  tone,
  testid,
}: {
  label: string;
  value: string;
  tone?: "pos" | "neg";
  testid: string;
}) {
  const toneClass =
    tone === "pos"
      ? "text-emerald-400"
      : tone === "neg"
        ? "text-rose-400"
        : "text-text-primary";
  return (
    <div
      className="rounded-card border border-border bg-bg-2 px-4 py-3"
      data-testid={testid}
    >
      <div className="text-xs uppercase tracking-wide text-text-muted">
        {label}
      </div>
      <div className={`text-lg font-semibold ${toneClass}`}>{value}</div>
    </div>
  );
}

function PositionsTable({
  positions,
  closing,
  onClose,
}: {
  positions: PaperPosition[];
  closing: Record<string, boolean>;
  onClose: (p: PaperPosition) => void;
}) {
  return (
    <div className="overflow-x-auto rounded-card border border-border">
      <table className="w-full text-left text-sm">
        <thead className="bg-bg-2 text-xs uppercase tracking-wide text-text-muted">
          <tr>
            <th className="px-3 py-2">Symbol</th>
            <th className="px-3 py-2 text-right">Qty</th>
            <th className="px-3 py-2 text-right">Avg entry</th>
            <th className="px-3 py-2 text-right">Current px</th>
            <th className="px-3 py-2 text-right">Unrealized P&L</th>
            <th className="px-3 py-2 text-right">%</th>
            <th className="px-3 py-2">Thesis</th>
            <th className="px-3 py-2 text-right" aria-label="actions" />
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => {
            const pnlTone = p.unrealized_pnl >= 0 ? "text-emerald-400" : "text-rose-400";
            const isClosing = Boolean(closing[p.symbol]);
            return (
              <tr
                key={p.symbol}
                data-testid="position-row"
                data-symbol={p.symbol}
                className="border-t border-border hover:bg-bg-3/40"
              >
                <td className="px-3 py-2 font-medium">{p.symbol}</td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {formatNum(p.qty, 0)}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {formatNum(p.avg_entry)}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {formatNum(p.current_px)}
                </td>
                <td className={`px-3 py-2 text-right tabular-nums ${pnlTone}`}>
                  {formatUsd(p.unrealized_pnl)}
                </td>
                <td className={`px-3 py-2 text-right tabular-nums ${pnlTone}`}>
                  {formatPct(p.unrealized_pnl_pct)}
                </td>
                <td className="px-3 py-2 text-xs text-text-secondary">
                  {p.thesis_id ? (
                    <a
                      className="underline decoration-dotted underline-offset-2 hover:text-primary"
                      href={`/track-record#${p.thesis_id}`}
                    >
                      {p.thesis_id.slice(0, 8)}
                    </a>
                  ) : (
                    <span className="text-text-muted">—</span>
                  )}
                </td>
                <td className="px-3 py-2 text-right">
                  <Button
                    variant="outline"
                    size="sm"
                    data-testid="close-position"
                    disabled={isClosing}
                    onClick={() => onClose(p)}
                  >
                    {isClosing ? "Closing…" : "Execute in paper"}
                  </Button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
