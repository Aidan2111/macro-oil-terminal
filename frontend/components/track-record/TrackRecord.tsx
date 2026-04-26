"use client";

import * as React from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { API_BASE } from "@/lib/api";
import { EmptyState } from "@/components/common/EmptyState";
import { LoadingSkeleton } from "@/components/common/LoadingSkeleton";
import { ChartErrorBoundary } from "@/components/common/ChartErrorBoundary";
import {
  computeEquityCurve,
  computeReturnHistogram,
  computeTrackStats,
} from "./stats";
import type { ThesisHistoryResponse, ThesisRow } from "./types";

type FetchState =
  | { status: "loading" }
  | { status: "ready"; rows: ThesisRow[] }
  | { status: "error"; message: string };

/**
 * Public, unauthenticated Track Record view.
 *
 * Hits `/api/thesis/history?limit=200` and does all the number-
 * crunching client-side so the reader can inspect the data without
 * a second round-trip. If the backend later adds `/api/thesis/stats`
 * we swap `computeTrackStats` for a direct fetch.
 */
export function TrackRecord() {
  const [state, setState] = React.useState<FetchState>({ status: "loading" });

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/thesis/history?limit=200`, {
          headers: { Accept: "application/json" },
        });
        if (!res.ok) {
          if (!cancelled)
            setState({
              status: "error",
              message: `Failed to load history (${res.status})`,
            });
          return;
        }
        const json = (await res.json()) as ThesisHistoryResponse;
        if (!cancelled)
          setState({ status: "ready", rows: json.theses ?? [] });
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
      <div data-testid="track-record" className="space-y-4">
        <LoadingSkeleton lines={6} height="h-5" />
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div data-testid="track-record">
        <EmptyState
          variant="chart"
          title="Track record unavailable"
          message={state.message}
        />
      </div>
    );
  }

  const rows = state.rows;
  if (rows.length === 0) {
    return (
      <div data-testid="track-record">
        <EmptyState
          variant="chart"
          title="No thesis history yet"
          message="Once the model has generated theses with outcomes, they show up here."
        />
      </div>
    );
  }

  return <TrackRecordReady rows={rows} />;
}

function TrackRecordReady({ rows }: { rows: ThesisRow[] }) {
  const stats = React.useMemo(() => computeTrackStats(rows), [rows]);
  const curve = React.useMemo(() => computeEquityCurve(rows), [rows]);
  const histogram = React.useMemo(() => computeReturnHistogram(rows), [rows]);

  const stanceData = (["long", "short", "flat"] as const).map((k) => ({
    stance: k,
    hit_rate_pct: stats.stance_outcomes[k].hit_rate * 100,
    total: stats.stance_outcomes[k].total,
  }));

  return (
    <div data-testid="track-record" className="space-y-6">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCell
          label="Hit rate"
          value={`${(stats.hit_rate * 100).toFixed(1)}%`}
          sub={`${stats.high_confidence_count} high-conf. calls`}
          testid="stat-hit-rate"
        />
        <StatCell
          label="Avg hold"
          value={`${stats.avg_hold_days.toFixed(1)}d`}
          testid="stat-avg-hold"
        />
        <StatCell
          label="Avg return"
          value={`${(stats.avg_return * 100).toFixed(2)}%`}
          tone={stats.avg_return >= 0 ? "pos" : "neg"}
          testid="stat-avg-return"
        />
        <StatCell
          label="Sharpe (signal)"
          value={stats.sharpe.toFixed(2)}
          testid="stat-sharpe"
        />
      </div>

      <ChartCard title="Equity curve (cumulative)">
        {curve.length === 0 ? (
          <InlineEmpty message="No closed trades to plot yet." />
        ) : (
          <ChartErrorBoundary label="Equity curve">
          <ResponsiveContainer width="100%" height={240}>
            <LineChart
              data={curve.map((p) => ({
                t: p.t.slice(0, 10),
                cum_return_pct: p.cum_return * 100,
              }))}
              margin={{ top: 10, right: 16, bottom: 0, left: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border, #1f2937)" />
              <XAxis dataKey="t" stroke="currentColor" fontSize={11} />
              <YAxis
                stroke="currentColor"
                fontSize={11}
                tickFormatter={(v) => `${Number(v).toFixed(1)}%`}
              />
              <Tooltip
                contentStyle={{ background: "#0b1220", border: "1px solid #1f2937" }}
              />
              <Line
                type="monotone"
                dataKey="cum_return_pct"
                stroke="#10b981"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
          </ChartErrorBoundary>
        )}
      </ChartCard>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <ChartCard title="Per-trade return distribution">
          {histogram.length === 0 ? (
            <InlineEmpty message="No returns to bucket yet." />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart
                data={histogram.map((b) => ({
                  bucket: `${(b.bucket * 100).toFixed(1)}%`,
                  count: b.count,
                  sign: b.bucket >= 0 ? "pos" : "neg",
                }))}
                margin={{ top: 10, right: 16, bottom: 0, left: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border, #1f2937)" />
                <XAxis dataKey="bucket" stroke="currentColor" fontSize={11} />
                <YAxis stroke="currentColor" fontSize={11} allowDecimals={false} />
                <Tooltip
                  contentStyle={{ background: "#0b1220", border: "1px solid #1f2937" }}
                />
                <Bar dataKey="count">
                  {histogram.map((b, i) => (
                    <Cell
                      key={`c${i}`}
                      fill={b.bucket >= 0 ? "#10b981" : "#f43f5e"}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartCard>

        <ChartCard title="Stance outcome — % that hit target">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart
              data={stanceData}
              margin={{ top: 10, right: 16, bottom: 0, left: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border, #1f2937)" />
              <XAxis dataKey="stance" stroke="currentColor" fontSize={11} />
              <YAxis
                stroke="currentColor"
                fontSize={11}
                domain={[0, 100]}
                tickFormatter={(v) => `${v}%`}
              />
              <Tooltip
                contentStyle={{ background: "#0b1220", border: "1px solid #1f2937" }}
                formatter={(v: number) => `${v.toFixed(1)}%`}
              />
              <Bar dataKey="hit_rate_pct" fill="#38bdf8" />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
    </div>
  );
}

function StatCell({
  label,
  value,
  sub,
  tone,
  testid,
}: {
  label: string;
  value: string;
  sub?: string;
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
      data-testid={testid}
      className="rounded-card border border-border bg-bg-2 px-4 py-3"
    >
      <div className="text-xs uppercase tracking-wide text-text-muted">
        {label}
      </div>
      <div className={`text-lg font-semibold ${toneClass}`}>{value}</div>
      {sub ? (
        <div className="text-[11px] text-text-muted">{sub}</div>
      ) : null}
    </div>
  );
}

function ChartCard({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-card border border-border bg-bg-2 p-4">
      <div className="mb-2 text-xs uppercase tracking-wide text-text-muted">
        {title}
      </div>
      {children}
    </div>
  );
}

function InlineEmpty({ message }: { message: string }) {
  return (
    <div className="py-8 text-center text-xs text-text-muted">{message}</div>
  );
}

export default TrackRecord;
