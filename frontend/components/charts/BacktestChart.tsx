"use client";

import * as React from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import type { BacktestLiveResponse } from "@/types/api";

type Props = {
  data: BacktestLiveResponse | null;
  error?: string | null;
  height?: number;
};

const AXIS_COLOR = "#94a3b8";
const GRID_COLOR = "rgba(255,255,255,0.06)";
const POSITIVE = "#10b981"; // emerald
const NEGATIVE = "#f43f5e"; // rose

/**
 * Equity-curve visualisation for POST /api/backtest. Above the chart
 * sits a stats strip (Sharpe / Sortino / Calmar / Hit / Max DD). The
 * area fills positive-equity cyan and drops into a rose shaded region
 * when the curve goes under water.
 */
export function BacktestChart({ data, error, height = 320 }: Props) {
  if (error) {
    return (
      <div data-testid="backtest-chart" aria-label="Backtest equity curve">
        <ErrorState message={error} />
      </div>
    );
  }
  if (!data || !data.equity_curve || data.equity_curve.length === 0) {
    return (
      <div data-testid="backtest-chart" aria-label="Backtest equity curve">
        <StatsRow data={data} />
        <EmptyState
          variant="chart"
          title="No backtest yet"
          message="Run the thesis backtest to plot the equity curve."
        />
      </div>
    );
  }

  const series = data.equity_curve
    .filter((p) => p.cum_pnl_usd != null && p.Date != null)
    .map((p) => ({ date: p.Date as string, pnl: p.cum_pnl_usd as number }));

  // Richer aria-label — surface the latest cumulative PnL + Sharpe so
  // AT users get the ground truth, not just "backtest equity curve".
  // Review #13 axis 7.
  const latest = series[series.length - 1]?.pnl ?? 0;
  const sharpe = data?.sharpe;
  const ariaLabel =
    series.length > 0
      ? `Backtest equity curve, latest cumulative PnL $${Math.round(latest).toLocaleString()}${
          sharpe != null && !Number.isNaN(sharpe)
            ? `, Sharpe ${sharpe.toFixed(2)}`
            : ""
        }`
      : "Backtest equity curve";

  return (
    <div
      data-testid="backtest-chart"
      aria-label={ariaLabel}
      role="img"
      className="w-full"
    >
      <StatsRow data={data} />
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={series} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
            <defs>
              <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={POSITIVE} stopOpacity={0.45} />
                <stop offset="50%" stopColor={POSITIVE} stopOpacity={0.08} />
                <stop offset="50%" stopColor={NEGATIVE} stopOpacity={0.08} />
                <stop offset="100%" stopColor={NEGATIVE} stopOpacity={0.45} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" />
            <XAxis
              dataKey="date"
              stroke={AXIS_COLOR}
              tick={{ fill: AXIS_COLOR, fontSize: 11 }}
              tickFormatter={(iso: string) => iso.slice(5)}
              aria-label="Date axis"
              minTickGap={32}
            />
            <YAxis
              stroke={AXIS_COLOR}
              tick={{ fill: AXIS_COLOR, fontSize: 11 }}
              width={60}
              tickFormatter={(v: number) => `$${Math.round(v).toLocaleString()}`}
              aria-label="Cumulative PnL axis"
            />
            <Tooltip
              cursor={{ stroke: AXIS_COLOR, strokeDasharray: "3 3" }}
              contentStyle={{
                background: "#0f1a2e",
                border: "1px solid #2a3245",
                borderRadius: 8,
                fontSize: 12,
              }}
              formatter={(value: number) => [
                `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`,
                "Cumulative PnL",
              ]}
            />
            <ReferenceLine y={0} stroke={AXIS_COLOR} strokeDasharray="2 2" />
            <Area
              type="monotone"
              dataKey="pnl"
              stroke={POSITIVE}
              strokeWidth={2}
              fill="url(#equityFill)"
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function StatsRow({ data }: { data: BacktestLiveResponse | null }) {
  const stats = [
    { label: "Sharpe", value: fmt(data?.sharpe) },
    { label: "Sortino", value: fmt(data?.sortino) },
    { label: "Calmar", value: fmt(data?.calmar) },
    { label: "Hit rate", value: pct(data?.hit_rate) },
    { label: "Max DD", value: usd(data?.max_drawdown) },
  ];
  return (
    <div className="grid grid-cols-5 gap-2 pb-3 text-xs">
      {stats.map((s) => (
        <div key={s.label} className="rounded-btn border border-border bg-bg-2 px-3 py-2">
          <div className="text-text-secondary">{s.label}</div>
          <div className="font-mono text-text-primary">{s.value}</div>
        </div>
      ))}
    </div>
  );
}

function fmt(v: number | null | undefined): string {
  return v == null || Number.isNaN(v) ? "--" : v.toFixed(2);
}
function pct(v: number | null | undefined): string {
  return v == null || Number.isNaN(v) ? "--" : `${(v * 100).toFixed(1)}%`;
}
function usd(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "--";
  return `$${Math.round(v).toLocaleString()}`;
}
