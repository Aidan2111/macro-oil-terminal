"use client";

import * as React from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import type { SpreadHistoryPoint } from "@/types/api";

type Props = {
  data: SpreadHistoryPoint[];
  error?: string | null;
  height?: number;
};

const AXIS_COLOR = "#94a3b8"; // slate-400
const GRID_COLOR = "rgba(255,255,255,0.06)";
const LINE_COLOR = "#22d3ee"; // cyan-400

/**
 * 90-day Brent-WTI spread line chart. Dark theme, subtle grid, cyan
 * stroke. The tooltip reformats the ISO date into a plain-English
 * string and prefixes value with "$".
 */
export function SpreadChart({ data, error, height = 300 }: Props) {
  if (error) {
    return (
      <div data-testid="spread-chart" aria-label="Brent-WTI spread chart">
        <ErrorState message={error} />
      </div>
    );
  }
  if (!data || data.length === 0) {
    return (
      <div data-testid="spread-chart" aria-label="Brent-WTI spread chart">
        <EmptyState
          variant="chart"
          title="No spread data yet"
          message="We'll draw the 90-day Brent-WTI line once the upstream returns data."
        />
      </div>
    );
  }

  const series = data
    .filter((d) => d.spread != null)
    .map((d) => ({ date: d.date, spread: d.spread as number }));

  // Build a richer aria-label with the latest value + 30d delta so AT
  // users get more than the static "spread chart" header. Review #13
  // axis 7.
  const latest = series[series.length - 1]?.spread ?? 0;
  const baselineIdx = Math.max(0, series.length - 31);
  const baseline = series[baselineIdx]?.spread ?? latest;
  const delta = latest - baseline;
  const sign = delta >= 0 ? "+" : "";
  const ariaLabel =
    series.length > 0
      ? `Brent–WTI spread chart, latest ${latest.toFixed(2)}, ${sign}${delta.toFixed(2)} last 30 days`
      : "Brent–WTI spread chart (90 days)";

  return (
    <div
      data-testid="spread-chart"
      aria-label={ariaLabel}
      role="img"
      className="w-full"
      style={{ height }}
    >
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={series} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" />
          <XAxis
            dataKey="date"
            stroke={AXIS_COLOR}
            tick={{ fill: AXIS_COLOR, fontSize: 11 }}
            tickFormatter={formatTickDate}
            minTickGap={28}
          />
          <YAxis
            stroke={AXIS_COLOR}
            tick={{ fill: AXIS_COLOR, fontSize: 11 }}
            tickFormatter={(v: number) => `$${v.toFixed(2)}`}
            width={60}
          />
          <Tooltip
            cursor={{ stroke: AXIS_COLOR, strokeDasharray: "3 3" }}
            contentStyle={{
              background: "#0f1a2e",
              border: "1px solid #2a3245",
              borderRadius: 8,
              fontSize: 12,
            }}
            labelFormatter={(label: string) => formatTooltipDate(label)}
            formatter={(value: number) => [`$${value.toFixed(2)}`, "Spread"]}
          />
          <Line
            type="monotone"
            dataKey="spread"
            stroke={LINE_COLOR}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function formatTickDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.getUTCMonth() + 1}/${d.getUTCDate()}`;
}

function formatTooltipDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, {
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}
