"use client";

import * as React from "react";
import {
  CartesianGrid,
  Label,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
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

const AXIS_COLOR = "#94a3b8";
const GRID_COLOR = "rgba(255,255,255,0.06)";
const LINE_COLOR = "#fbbf24"; // amber — stretch is a warn signal
const BAND_BOUND = 2.3;

/**
 * 90-day rolling Z-score (renamed "Spread Stretch") with horizontal
 * reference lines at the ±2.3 Stretched boundary and a shaded band
 * highlighting the qualitative zone the latest value sits in.
 */
export function StretchChart({ data, error, height = 300 }: Props) {
  if (error) {
    return (
      <div data-testid="stretch-chart" aria-label="Spread Stretch chart">
        <ErrorState message={error} />
      </div>
    );
  }
  if (!data || data.length === 0) {
    return (
      <div data-testid="stretch-chart" aria-label="Spread Stretch chart">
        <EmptyState
          variant="chart"
          title="No stretch data"
          message="Rolling Z-scores will plot here once we have 90 bars."
        />
      </div>
    );
  }

  const series = data
    .filter((d) => d.z_score != null)
    .map((d) => ({ date: d.date, z: d.z_score as number }));

  const latest = series[series.length - 1]?.z ?? 0;
  const bandY1 = Math.sign(latest) >= 0 ? BAND_BOUND : -BAND_BOUND;
  const bandY2 = Math.sign(latest) >= 0 ? 4 : -4;
  const bandColor =
    Math.abs(latest) >= BAND_BOUND
      ? "rgba(244,63,94,0.10)"
      : "rgba(34,211,238,0.08)";

  return (
    <div
      data-testid="stretch-chart"
      aria-label="Spread Stretch — rolling 90d Z-score"
      role="img"
      className="w-full"
      style={{ height }}
    >
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={series} margin={{ top: 16, right: 24, bottom: 8, left: 8 }}>
          <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" />
          <XAxis
            dataKey="date"
            stroke={AXIS_COLOR}
            tick={{ fill: AXIS_COLOR, fontSize: 11 }}
            tickFormatter={(iso: string) => iso.slice(5)}
            aria-label="Date axis"
            minTickGap={28}
          />
          <YAxis
            domain={[-4, 4]}
            stroke={AXIS_COLOR}
            tick={{ fill: AXIS_COLOR, fontSize: 11 }}
            width={40}
            aria-label="Z-score axis"
          />
          <ReferenceArea
            y1={bandY1}
            y2={bandY2}
            fill={bandColor}
            strokeOpacity={0}
            ifOverflow="extendDomain"
          />
          <ReferenceLine y={BAND_BOUND} stroke="#f43f5e" strokeDasharray="4 4">
            <Label
              value="Very Stretched"
              position="insideTopRight"
              fill="#f43f5e"
              fontSize={11}
            />
          </ReferenceLine>
          <ReferenceLine y={-BAND_BOUND} stroke="#f43f5e" strokeDasharray="4 4" />
          <ReferenceLine y={0} stroke={AXIS_COLOR} strokeDasharray="2 2">
            <Label
              value="Calm"
              position="insideBottomRight"
              fill={AXIS_COLOR}
              fontSize={11}
            />
          </ReferenceLine>
          <Tooltip
            cursor={{ stroke: AXIS_COLOR, strokeDasharray: "3 3" }}
            contentStyle={{
              background: "#0f1a2e",
              border: "1px solid #2a3245",
              borderRadius: 8,
              fontSize: 12,
            }}
            formatter={(value: number) => [value.toFixed(2), "Stretch (σ)"]}
          />
          <Line
            type="monotone"
            dataKey="z"
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
