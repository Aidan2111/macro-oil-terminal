"use client";

import * as React from "react";
import type {
  FreshnessBadge,
  HealthStatus,
  ProviderHealth,
  ProviderName,
} from "@/types/api";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { useDataQuality } from "@/lib/hooks/use-data-quality";

const PROVIDER_LABELS: Record<ProviderName, string> = {
  yfinance: "yfinance",
  eia: "EIA",
  cftc: "CFTC",
  aisstream: "AISStream",
  aisstream_secondary: "AIS 2°",
  alpaca_paper: "Alpaca",
  audit_log: "Thesis log",
  hormuz: "Hormuz",
  iran_production: "Iran prod.",
  iran_tankers: "Iran tankers",
  news_rss: "News",
  ofac: "OFAC",
  russia: "Russia",
};

const STATUS_DOT: Record<HealthStatus, string> = {
  green: "bg-emerald-500 shadow-[0_0_0_3px_rgba(16,185,129,0.15)]",
  amber: "bg-amber-400 shadow-[0_0_0_3px_rgba(251,191,36,0.15)]",
  red: "bg-rose-500 shadow-[0_0_0_3px_rgba(244,63,94,0.15)]",
};

const STATUS_LABEL: Record<HealthStatus, string> = {
  green: "Live",
  amber: "Degraded",
  red: "Stale",
};

const PILL_CLASSES: Record<HealthStatus, string> = {
  green: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  amber: "border-amber-400/40 bg-amber-400/10 text-amber-300",
  red: "border-rose-500/40 bg-rose-500/10 text-rose-300",
};

/**
 * Compact relative-time formatter — "2m ago", "3h ago", "5d ago".
 * Returns "—" when the timestamp is null or unparseable.
 */
function relTime(iso: string | null): string {
  if (!iso) return "—";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "—";
  const ageS = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (ageS < 60) return `${ageS}s ago`;
  const ageM = Math.floor(ageS / 60);
  if (ageM < 60) return `${ageM}m ago`;
  const ageH = Math.floor(ageM / 60);
  if (ageH < 24) return `${ageH}h ago`;
  const ageD = Math.floor(ageH / 24);
  return `${ageD}d ago`;
}

/**
 * Per-provider tooltip body — surfaces last-good time, observation
 * count, latency, freshness SLA, and any guard message.
 */
function ProviderTooltipBody({ p }: { p: ProviderHealth }) {
  return (
    <div className="space-y-1 text-xs">
      <div className="font-semibold">{PROVIDER_LABELS[p.name]}</div>
      <div className="text-text-secondary">
        Status: <span className="font-mono">{STATUS_LABEL[p.status]}</span>
      </div>
      <div className="text-text-secondary">
        Last good: {relTime(p.last_good_at)}
      </div>
      {p.n_obs !== null ? (
        <div className="text-text-secondary">
          Observations: <span className="num">{p.n_obs}</span>
        </div>
      ) : null}
      {p.latency_ms !== null ? (
        <div className="text-text-secondary">
          Latency: <span className="num">{p.latency_ms}</span> ms
        </div>
      ) : null}
      <div className="text-text-muted">
        SLA: &lt; <span className="num">{p.freshness_target_hours}</span> h
      </div>
      {p.message ? (
        <div className="pt-1 text-amber-300">{p.message}</div>
      ) : null}
    </div>
  );
}

/**
 * 5-cell (plus audit-log) grid showing per-provider health.
 *
 * Mounts client-side only and lazily polls /api/data-quality every
 * 60 s. The first fetch is fired on mount; we don't SSR this tile
 * because it's secondary content below the hero card and we don't
 * want it on the LCP critical path.
 */
export function DataQualityTile() {
  const { envelope: env, error, badge } = useDataQuality();

  if (error && !env) {
    return (
      <div
        data-testid="data-quality-error"
        className="rounded-card border border-border bg-bg-2 p-4 text-xs text-text-secondary"
      >
        Data quality: {error}
      </div>
    );
  }

  if (!env) {
    return (
      <div
        data-testid="data-quality-loading"
        className="rounded-card border border-border bg-bg-2 p-4 text-xs text-text-muted"
        aria-busy="true"
      >
        Loading data quality…
      </div>
    );
  }

  return (
    <TooltipProvider delayDuration={120}>
      <div
        data-testid="data-quality-tile"
        className="rounded-card border border-border bg-bg-2 p-4"
      >
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
            Data quality
          </h3>
          <span
            data-testid="data-quality-overall"
            className="inline-flex items-center gap-2 text-xs text-text-secondary"
          >
            <span
              aria-hidden
              className={cn("h-2 w-2 rounded-full", STATUS_DOT[env.overall])}
            />
            {STATUS_LABEL[env.overall]}
          </span>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-7">
          {env.providers.map((p) => {
            const b: FreshnessBadge | undefined = badge(p.name);
            const tier: HealthStatus = b?.tier ?? p.status;
            const ageLabel = b?.age_label ?? relTime(p.last_good_at);
            return (
              <Tooltip key={p.name}>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    data-testid={`data-quality-cell-${p.name}`}
                    data-status={p.status}
                    data-tier={tier}
                    className="flex flex-col items-start gap-1 rounded-btn border border-border bg-bg-1 px-3 py-2 text-left text-xs hover:bg-bg-3 focus:outline-none focus:ring-2 focus:ring-accent"
                  >
                    <span className="flex items-center gap-2">
                      <span
                        aria-hidden
                        className={cn(
                          "h-2 w-2 rounded-full",
                          STATUS_DOT[tier],
                        )}
                      />
                      <span className="font-medium text-text-primary">
                        {PROVIDER_LABELS[p.name] ?? p.name}
                      </span>
                    </span>
                    {/* Issue #108 freshness pill — always renders the
                        age label; colours by tier so amber/red are
                        visible at a glance without opening the
                        tooltip. */}
                    <span
                      data-testid={`data-quality-pill-${p.name}`}
                      className={cn(
                        "inline-flex items-center rounded-full border px-2 py-[1px] text-[10px] font-medium leading-none",
                        PILL_CLASSES[tier],
                      )}
                    >
                      {ageLabel}
                    </span>
                  </button>
                </TooltipTrigger>
                <TooltipContent side="top" className="max-w-xs">
                  <ProviderTooltipBody p={p} />
                </TooltipContent>
              </Tooltip>
            );
          })}
        </div>
      </div>
    </TooltipProvider>
  );
}

export default DataQualityTile;
