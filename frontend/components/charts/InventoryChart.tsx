"use client";

import * as React from "react";
import {
  CartesianGrid,
  ComposedChart,
  Label,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import type { DepletionForecast, InventoryPoint } from "@/types/api";

type Props = {
  history: InventoryPoint[];
  forecast: DepletionForecast | null;
  error?: string | null;
  height?: number;
};

const AXIS_COLOR = "#94a3b8";
const GRID_COLOR = "rgba(255,255,255,0.06)";
const TOTAL_COLOR = "#22d3ee"; // cyan
const PROJECT_COLOR = "#fbbf24"; // amber (dashed forecast)
const CUSHING_COLOR = "#f43f5e"; // rose

/**
 * 2-year commercial-crude line with a 1-year linear-regression
 * projection (dashed) and a twin Cushing overlay on the secondary
 * axis. If `forecast.projected_floor_date` is set, a vertical marker
 * flags the forecast breach.
 */
export function InventoryChart({
  history,
  forecast,
  error,
  height = 320,
}: Props) {
  if (error) {
    return (
      <div data-testid="inventory-chart" aria-label="US crude inventory chart">
        <ErrorState message={error} />
      </div>
    );
  }
  if (!history || history.length === 0) {
    return (
      <div data-testid="inventory-chart" aria-label="US crude inventory chart">
        <EmptyState
          variant="barrel"
          title="No inventory data"
          message="Weekly EIA stocks will render here once the feed returns."
        />
      </div>
    );
  }

  const totalSeries = history
    .filter((r) => r.total_bbls != null)
    .map((r) => ({ date: r.date, total: r.total_bbls as number }));

  // Linear regression on the last 52 weeks → project 52 weeks forward.
  const projection = buildProjection(totalSeries, 52, 52);

  const merged: Array<{
    date: string;
    total?: number;
    projection?: number;
    cushing?: number;
  }> = [...totalSeries];
  // Append projection past the last observed row.
  for (const p of projection) {
    merged.push({ date: p.date, projection: p.value });
  }
  // Overlay Cushing on matching dates.
  const cushingByDate = new Map(
    history
      .filter((r) => r.cushing_bbls != null)
      .map((r) => [r.date, r.cushing_bbls as number]),
  );
  for (const row of merged) {
    const v = cushingByDate.get(row.date);
    if (v != null) row.cushing = v;
  }

  const breachDate = forecast?.projected_floor_date ?? null;

  return (
    <div
      data-testid="inventory-chart"
      aria-label="US crude inventory — 2y history plus projection"
      role="img"
      className="w-full"
      style={{ height }}
    >
      {breachDate ? (
        <div className="pb-2 text-xs text-text-secondary">
          Forecast breach: <span className="text-warn">{breachDate}</span>
        </div>
      ) : null}
      <ResponsiveContainer width="100%" height={breachDate ? height - 24 : height}>
        <ComposedChart
          data={merged}
          margin={{ top: 8, right: 48, bottom: 8, left: 8 }}
        >
          <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" />
          <XAxis
            dataKey="date"
            stroke={AXIS_COLOR}
            tick={{ fill: AXIS_COLOR, fontSize: 11 }}
            tickFormatter={(iso: string) => iso.slice(0, 7)}
            minTickGap={32}
          />
          <YAxis
            yAxisId="total"
            stroke={AXIS_COLOR}
            tick={{ fill: AXIS_COLOR, fontSize: 11 }}
            tickFormatter={(v: number) => `${Math.round(v / 1_000_000)}M`}
            width={52}
          />
          <YAxis
            yAxisId="cushing"
            orientation="right"
            stroke={CUSHING_COLOR}
            tick={{ fill: CUSHING_COLOR, fontSize: 11 }}
            tickFormatter={(v: number) => `${Math.round(v / 1_000_000)}M`}
            width={48}
          />
          <Tooltip
            cursor={{ stroke: AXIS_COLOR, strokeDasharray: "3 3" }}
            contentStyle={{
              background: "#0f1a2e",
              border: "1px solid #2a3245",
              borderRadius: 8,
              fontSize: 12,
            }}
            formatter={(value: number, name: string) => [
              `${(value / 1_000_000).toFixed(1)}M bbls`,
              name,
            ]}
          />
          {breachDate ? (
            <ReferenceLine
              yAxisId="total"
              x={breachDate}
              stroke="#f43f5e"
              strokeDasharray="6 4"
            >
              <Label
                value="Forecast breach"
                position="insideTopRight"
                fill="#f43f5e"
                fontSize={11}
              />
            </ReferenceLine>
          ) : null}
          <Line
            yAxisId="total"
            type="monotone"
            dataKey="total"
            name="Commercial+SPR"
            stroke={TOTAL_COLOR}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
            connectNulls
          />
          <Line
            yAxisId="total"
            type="monotone"
            dataKey="projection"
            name="1y projection"
            stroke={PROJECT_COLOR}
            strokeWidth={2}
            strokeDasharray="6 4"
            dot={false}
            isAnimationActive={false}
            connectNulls
          />
          <Line
            yAxisId="cushing"
            type="monotone"
            dataKey="cushing"
            name="Cushing"
            stroke={CUSHING_COLOR}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
            connectNulls
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

type ProjectionPoint = { date: string; value: number };

function buildProjection(
  series: { date: string; total: number }[],
  fitWindow: number,
  forwardWeeks: number,
): ProjectionPoint[] {
  if (series.length < Math.min(8, fitWindow)) return [];
  const window = series.slice(-fitWindow);
  const xs = window.map((_, i) => i);
  const ys = window.map((r) => r.total);
  const n = xs.length;
  const sumX = xs.reduce((a, b) => a + b, 0);
  const sumY = ys.reduce((a, b) => a + b, 0);
  const sumXY = xs.reduce((acc, x, i) => acc + x * ys[i], 0);
  const sumXX = xs.reduce((acc, x) => acc + x * x, 0);
  const denom = n * sumXX - sumX * sumX;
  if (denom === 0) return [];
  const slope = (n * sumXY - sumX * sumY) / denom;
  const intercept = (sumY - slope * sumX) / n;

  const lastDate = new Date(window[window.length - 1].date);
  const out: ProjectionPoint[] = [];
  for (let i = 1; i <= forwardWeeks; i++) {
    const d = new Date(lastDate);
    d.setUTCDate(d.getUTCDate() + i * 7);
    const yhat = intercept + slope * (n - 1 + i);
    out.push({ date: d.toISOString().slice(0, 10), value: yhat });
  }
  return out;
}
