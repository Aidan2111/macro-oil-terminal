import type { BacktestLiveResponse } from "@/types/api";

/**
 * Deterministic fixture mimicking POST /api/backtest — a 200-bar
 * cumulative-PnL curve with plausible drawdowns.
 */
export function makeBacktestFixture(points = 200): BacktestLiveResponse {
  let cum = 0;
  const equity_curve = Array.from({ length: points }, (_, i) => {
    const d = new Date("2025-01-01T00:00:00Z");
    d.setUTCDate(d.getUTCDate() + i);
    const bar = Math.sin(i / 9) * 800 + 120;
    cum += bar;
    return {
      Date: d.toISOString().slice(0, 10),
      cum_pnl_usd: cum,
    };
  });
  return {
    sharpe: 1.42,
    sortino: 1.91,
    calmar: 0.87,
    var_95: -1800,
    es_95: -2400,
    max_drawdown: -4200,
    hit_rate: 0.58,
    total_pnl_usd: cum,
    n_trades: 24,
    avg_days_held: 8.3,
    avg_pnl_per_bbl: 0.41,
    rolling_12m_sharpe: 1.38,
    equity_curve,
    trades: [],
    params: { entry_z: 2.0, exit_z: 0.2, lookback_days: 365 },
  };
}
