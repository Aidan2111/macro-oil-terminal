"use client";

import * as React from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ComposedChart,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { API_BASE } from "@/lib/api";

type BucketStat = {
  label: string;
  lo: number;
  hi: number;
  midpoint: number;
  n: number;
  hits: number;
  hit_rate: number;
};

type CalibrationStats = {
  n_total: number;
  brier_score: number;
  mean_signed_error: number;
  verdict: "calibrated" | "overconfident" | "underconfident" | "noisy" | "insufficient_data";
  buckets: BucketStat[];
};

type State =
  | { status: "loading" }
  | { status: "ready"; stats: CalibrationStats }
  | { status: "error"; message: string };

/**
 * 4-bar reliability diagram for the public /track-record page.
 *
 * Bars: realised hit-rate per stated-confidence bucket.
 * Reference line: y=x ideal calibration.
 * Badge: "calibrated", "overconfident", "underconfident", or "noisy",
 * driven by the Brier score + signed-error verdict from the backend.
 */
export function CalibrationChart() {
  const [state, setState] = React.useState<State>({ status: "loading" });

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/calibration?limit=200`, {
          headers: { Accept: "application/json" },
        });
        if (!res.ok) {
          if (!cancelled)
            setState({
              status: "error",
              message: `Failed to load calibration (${res.status})`,
            });
          return;
        }
        const json = (await res.json()) as CalibrationStats;
        if (!cancelled) setState({ status: "ready", stats: json });
      } catch (err) {
        if (!cancelled)
          setState({ status: "error", message: String(err) });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (state.status === "loading") {
    return (
      <div
        data-testid="calibration-chart"
        className="rounded-card border border-border bg-bg-2 p-4"
      >
        <div className="text-xs uppercase tracking-wide text-text-muted">
          Confidence calibration
        </div>
        <div className="py-12 text-center text-xs text-text-muted">
          Loading calibration data...
        </div>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div
        data-testid="calibration-chart"
        className="rounded-card border border-border bg-bg-2 p-4"
      >
        <div className="text-xs uppercase tracking-wide text-text-muted">
          Confidence calibration
        </div>
        <div className="py-12 text-center text-xs text-rose-300">
          {state.message}
        </div>
      </div>
    );
  }

  const { stats } = state;
  const buckets = stats.buckets ?? [];
  const data = buckets.map((b) => ({
    bucket: b.label,
    midpoint_pct: b.midpoint * 100,
    hit_rate_pct: b.hit_rate * 100,
    n: b.n,
  }));

  const verdictTone =
    stats.verdict === "calibrated"
      ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-200"
      : stats.verdict === "overconfident"
        ? "border-rose-500/40 bg-rose-500/10 text-rose-200"
        : stats.verdict === "underconfident"
          ? "border-amber-500/40 bg-amber-500/10 text-amber-200"
          : "border-slate-500/40 bg-slate-500/10 text-slate-200";

  const verdictLabel =
    stats.verdict === "calibrated"
      ? "well-calibrated"
      : stats.verdict === "overconfident"
        ? "overconfident"
        : stats.verdict === "underconfident"
          ? "underconfident"
          : stats.verdict === "noisy"
            ? "noisy (high Brier)"
            : "not enough data";

  return (
    <div
      data-testid="calibration-chart"
      className="rounded-card border border-border bg-bg-2 p-4"
    >
      <div className="mb-2 flex items-center justify-between">
        <div className="text-xs uppercase tracking-wide text-text-muted">
          Confidence calibration
        </div>
        <span
          className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium ${verdictTone}`}
        >
          {verdictLabel}
        </span>
      </div>
      <div className="mb-3 text-[11px] text-text-muted">
        Brier {(stats.brier_score ?? 0).toFixed(3)} - signed error{" "}
        {((stats.mean_signed_error ?? 0) * 100).toFixed(1)}% - n=
        {stats.n_total ?? 0}
      </div>
      <ResponsiveContainer width="100%" height={240}>
        <ComposedChart
          data={data}
          margin={{ top: 10, right: 16, bottom: 0, left: 0 }}
        >
          <CartesianGrid
            strokeDasharray="3 3"
            stroke="var(--color-border, #1f2937)"
          />
          <XAxis dataKey="bucket" stroke="currentColor" fontSize={11} />
          <YAxis
            stroke="currentColor"
            fontSize={11}
            domain={[0, 100]}
            tickFormatter={(v) => `${v}%`}
          />
          <Tooltip
            contentStyle={{
              background: "#0b1220",
              border: "1px solid #1f2937",
            }}
            formatter={(v: number) => `${v.toFixed(1)}%`}
          />
          <ReferenceLine
            stroke="#94a3b8"
            strokeDasharray="4 4"
            ifOverflow="extendDomain"
            segment={[
              { x: "0-25%", y: 12.5 },
              { x: "75-100%", y: 87.5 },
            ]}
            label={{
              value: "ideal",
              position: "insideTopRight",
              fill: "#94a3b8",
              fontSize: 10,
            }}
          />
          <Bar dataKey="hit_rate_pct" name="realised hit rate">
            {data.map((d, i) => (
              <Cell
                key={`c${i}`}
                fill={d.hit_rate_pct >= d.midpoint_pct ? "#10b981" : "#f43f5e"}
              />
            ))}
          </Bar>
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export default CalibrationChart;
