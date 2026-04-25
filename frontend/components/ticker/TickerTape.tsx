"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { API_BASE, fetchJson } from "@/lib/api";
import { cn } from "@/lib/utils";
import type {
  InventoryLiveResponse,
  SpreadHistoryPoint,
  SpreadLiveResponse,
} from "@/types/api";

type TileData = {
  key: string;
  symbol: string;
  name: string;
  current: number;
  prev: number | null;
  unit: "usd" | "mbbl";
  sparkline: number[];
};

/**
 * Horizontal scrolling ticker tape. Four tiles — Brent, WTI, Spread,
 * Inventory — built from `/api/spread` + `/api/inventory`. Subscribes
 * to `/api/spread/stream` when the server supports SSE; otherwise
 * React Query polling keeps the tile fresh every 30s.
 *
 * On mobile the marquee gets out of the way: tiles wrap into rows
 * with no animation.
 */
export function TickerTape() {
  const spreadQ = useQuery<SpreadLiveResponse>({
    queryKey: ["spread"],
    queryFn: () => fetchJson<SpreadLiveResponse>("/api/spread"),
    refetchInterval: 30_000,
    staleTime: 25_000,
  });
  const invQ = useQuery<InventoryLiveResponse>({
    queryKey: ["inventory"],
    queryFn: () => fetchJson<InventoryLiveResponse>("/api/inventory"),
    refetchInterval: 60_000,
    staleTime: 55_000,
  });

  // Optional SSE upgrade — attempts to subscribe but silently falls
  // back to polling on 404/network error. The refetch call just
  // invalidates the cached snapshot so React Query refetches on the
  // next tick.
  React.useEffect(() => {
    if (typeof window === "undefined") return;
    const ES = (window as typeof window & { EventSource?: typeof EventSource })
      .EventSource;
    if (!ES) return;
    let closed = false;
    let source: EventSource | null = null;
    try {
      // Use the absolute API_BASE — static export doesn't proxy
      // /api/* on the SWA host, so a relative URL would 404 to HTML
      // and the browser would log an EventSource MIME-type error.
      source = new ES(`${API_BASE}/api/spread/stream`);
      source.onmessage = () => {
        if (!closed) spreadQ.refetch();
      };
      source.onerror = () => {
        source?.close();
      };
    } catch {
      // Ignore — polling already running.
    }
    return () => {
      closed = true;
      source?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const tiles: TileData[] = React.useMemo(
    () => buildTiles(spreadQ.data, invQ.data),
    [spreadQ.data, invQ.data],
  );

  const unavailable =
    spreadQ.isError && invQ.isError && tiles.every((t) => t.current === 0);

  return (
    <div
      data-testid="ticker-tape"
      aria-label="Live market ticker"
      className={cn(
        "border-b border-border bg-bg-2/80 backdrop-blur",
        "relative w-full",
      )}
    >
      {unavailable ? (
        <div className="px-4 py-2 text-xs text-text-secondary">
          Live ticker unavailable — retrying.
        </div>
      ) : (
        <>
          {/* Desktop/tablet: horizontal marquee, pauses on hover. */}
          <div className="hidden md:block overflow-hidden group">
            <ul
              className="flex w-max animate-scroll gap-6 px-4 py-2 group-hover:[animation-play-state:paused]"
              aria-live="polite"
            >
              {tiles.map((t) => (
                <TickerTile key={`a-${t.key}`} tile={t} />
              ))}
              {/* Duplicate for seamless loop. */}
              {tiles.map((t) => (
                <TickerTile key={`b-${t.key}`} tile={t} />
              ))}
            </ul>
          </div>
          {/* Mobile: flex-wrap — no animation. */}
          <ul className="md:hidden flex flex-wrap gap-2 px-2 py-2" aria-live="polite">
            {tiles.map((t) => (
              <TickerTile key={`m-${t.key}`} tile={t} />
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function TickerTile({ tile }: { tile: TileData }) {
  const delta =
    tile.prev != null ? tile.current - tile.prev : 0;
  const deltaPct =
    tile.prev != null && tile.prev !== 0
      ? (delta / tile.prev) * 100
      : 0;
  const color =
    delta > 0
      ? "text-emerald-500"
      : delta < 0
        ? "text-rose-500"
        : "text-slate-400";
  const sign = delta > 0 ? "+" : delta < 0 ? "" : "";

  return (
    <li
      className="flex shrink-0 items-center gap-3 rounded-btn border border-border bg-bg-3/40 px-3 py-1 text-xs"
      aria-label={`${tile.name} ${tile.current.toFixed(2)}`}
    >
      <span className="font-mono uppercase tracking-wide text-text-secondary">
        {tile.symbol}
      </span>
      <span className="text-text-primary">{tile.name}</span>
      <span className="font-mono text-text-primary">
        {formatValue(tile.current, tile.unit)}
      </span>
      <span className={cn("font-mono", color)}>
        {sign}
        {delta.toFixed(2)} ({sign}
        {deltaPct.toFixed(2)}%)
      </span>
      <Sparkline values={tile.sparkline} color={colorHex(delta)} />
    </li>
  );
}

function Sparkline({ values, color }: { values: number[]; color: string }) {
  const width = 80;
  const height = 22;
  if (!values || values.length < 2) {
    return (
      <svg
        data-testid="ticker-sparkline"
        width={width}
        height={height}
        aria-hidden
      />
    );
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const step = width / (values.length - 1);
  const d = values
    .map((v, i) => {
      const x = i * step;
      const y = height - ((v - min) / range) * (height - 2) - 1;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg
      data-testid="ticker-sparkline"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      aria-hidden
    >
      <path d={d} fill="none" stroke={color} strokeWidth={1.5} />
    </svg>
  );
}

function colorHex(delta: number): string {
  if (delta > 0) return "#10b981";
  if (delta < 0) return "#f43f5e";
  return "#94a3b8";
}

function formatValue(v: number, unit: "usd" | "mbbl"): string {
  if (unit === "mbbl") {
    return `${(v / 1_000).toFixed(0)} Mbbl`;
  }
  return `$${v.toFixed(2)}`;
}

function buildTiles(
  spread: SpreadLiveResponse | undefined,
  inventory: InventoryLiveResponse | undefined,
): TileData[] {
  const history = spread?.history ?? [];

  const brentSpark = pickSpark(history, "brent");
  const wtiSpark = pickSpark(history, "wti");
  const spreadSpark = pickSpark(history, "spread");

  const brentPrev = brentSpark.length >= 2 ? brentSpark[brentSpark.length - 2] : null;
  const wtiPrev = wtiSpark.length >= 2 ? wtiSpark[wtiSpark.length - 2] : null;
  const spreadPrev =
    spreadSpark.length >= 2 ? spreadSpark[spreadSpark.length - 2] : null;

  const invHistory = inventory?.history ?? [];
  const invSpark = invHistory
    .filter((r) => r.commercial_bbls != null)
    .map((r) => (r.commercial_bbls as number) / 1_000) // -> Mbbl
    .slice(-60);
  const invCurrentMbbl =
    inventory?.commercial_bbls != null
      ? inventory.commercial_bbls / 1_000
      : invSpark[invSpark.length - 1] ?? 0;
  const invPrev = invSpark.length >= 2 ? invSpark[invSpark.length - 2] : null;

  return [
    {
      key: "brent",
      symbol: "BZ",
      name: "Brent",
      current: spread?.brent ?? 0,
      prev: brentPrev,
      unit: "usd",
      sparkline: brentSpark,
    },
    {
      key: "wti",
      symbol: "CL",
      name: "WTI",
      current: spread?.wti ?? 0,
      prev: wtiPrev,
      unit: "usd",
      sparkline: wtiSpark,
    },
    {
      key: "spread",
      symbol: "BZ-CL",
      name: "Spread",
      current: spread?.spread ?? 0,
      prev: spreadPrev,
      unit: "usd",
      sparkline: spreadSpark,
    },
    {
      key: "inv",
      symbol: "USCRUDE",
      name: "Inventory",
      current: invCurrentMbbl,
      prev: invPrev,
      unit: "mbbl",
      sparkline: invSpark,
    },
  ];
}

function pickSpark(
  history: SpreadHistoryPoint[],
  field: "brent" | "wti" | "spread",
): number[] {
  return history
    .map((p) => p[field])
    .filter((v): v is number => v != null)
    .slice(-60);
}
