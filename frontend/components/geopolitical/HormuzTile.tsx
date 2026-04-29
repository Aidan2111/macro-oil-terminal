"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AreaChart,
  Area,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { fetchJson } from "@/lib/api";
import { ChartShimmer } from "@/components/illustrations/ChartShimmer";
import type { HormuzTransitResponse } from "@/types/api";

// ---- Percentile badge color logic -----------------------------------

function percentileBadgeClass(pct: number): string {
  if (pct >= 80) {
    // High percentile = supply stress signal = rose/red
    return "bg-rose-500/20 text-rose-400";
  }
  if (pct >= 40) {
    // Mid percentile = amber warning
    return "bg-amber-400/20 text-amber-300";
  }
  // Low percentile = normal/low risk = emerald green
  return "bg-emerald-500/20 text-emerald-400";
}

// ---- HormuzTile component -------------------------------------------

export function HormuzTile() {
  const { data, isLoading, isError } = useQuery<HormuzTransitResponse>({
    queryKey: ["hormuz"],
    queryFn: () => fetchJson<HormuzTransitResponse>("/api/geopolitical/hormuz"),
    refetchInterval: 60_000,
  });

  if (isLoading) {
    return <ChartShimmer height={140} bars={10} />;
  }

  if (isError || !data) {
    return (
      <div
        data-testid="hormuz-tile"
        className="rounded-card border border-border bg-bg-2 p-4"
      >
        <p className="text-xs text-text-secondary">
          Hormuz transit data unavailable.
        </p>
      </div>
    );
  }

  const { count_24h, percentile_1y, trend_30d } = data;

  return (
    <div
      data-testid="hormuz-tile"
      className="rounded-card border border-border bg-bg-2 p-4"
    >
      {/* Header */}
      <h3 className="text-xs font-semibold uppercase tracking-wider text-text-secondary mb-3">
        Hormuz transits
      </h3>

      {/* Hero count + percentile badge */}
      <div className="flex items-center gap-3 mb-2">
        <span
          data-testid="hormuz-count"
          className="text-4xl font-bold num text-cyan-400"
        >
          {count_24h}
        </span>

        <span
          data-testid="hormuz-percentile"
          className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${percentileBadgeClass(percentile_1y)}`}
        >
          {percentile_1y.toFixed(0)}th pct
        </span>
      </div>

      {/* Sub-label */}
      <p className="text-xs text-text-secondary mb-3">
        24h transits · Strait of Hormuz (~26.5°N 56.3°E, 50nm radius)
      </p>

      {/* 30-day sparkline */}
      <div data-testid="hormuz-sparkline">
        <ResponsiveContainer width="100%" height={80}>
          <AreaChart data={trend_30d}>
            <Area
              type="monotone"
              dataKey="count"
              stroke="#22d3ee"
              fill="rgba(34,211,238,0.08)"
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
            />
            <Tooltip
              contentStyle={{
                background: "#0f1a2e",
                border: "1px solid #2a3245",
                fontSize: 11,
              }}
              formatter={(v: number) => [v, "transits"]}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default HormuzTile;
