/**
 * useDataQuality() — issue #108
 *
 * Polls /api/data-quality on a configurable interval and exposes the
 * envelope + a per-provider lookup for the new freshness badges.
 *
 * Tiles can replace their bespoke fetch loops with:
 *
 *     const { envelope, badge, isStale, error } = useDataQuality();
 *     if (badge("yfinance")?.hide_content) return <RedFallback />;
 *
 * The hook is SSR-safe — it only fires the fetch in a useEffect, so
 * components that use it can still be statically rendered.
 */

"use client";

import * as React from "react";
import { fetchJson, ApiError } from "@/lib/api";
import type {
  DataQualityEnvelope,
  FreshnessBadge,
  ProviderName,
} from "@/types/api";

const DEFAULT_POLL_MS = 60_000;

export type UseDataQualityResult = {
  envelope: DataQualityEnvelope | null;
  /** Per-provider freshness badge lookup. Returns undefined when the
   *  backend hasn't deployed the badges block yet (older API). */
  badge: (name: string) => FreshnessBadge | undefined;
  /** True iff the named provider is in amber or red. Convenience
   *  wrapper around the badges array; falls back to the legacy
   *  status field when badges aren't present. */
  isStale: (name: ProviderName | string) => boolean;
  /** True iff /api/data-quality reports any provider in red. Used by
   *  page-level banners to nudge "things are degraded". */
  anyRed: boolean;
  /** Names of providers currently amber-or-red. Empty when fresh. */
  staleProviders: string[];
  /** Most recent fetch error message; null when last fetch was OK. */
  error: string | null;
  /** Initial-load gate. False after the first response (success or
   *  failure) lands. */
  loading: boolean;
};

export function useDataQuality(
  options: { pollIntervalMs?: number } = {},
): UseDataQualityResult {
  const pollIntervalMs = options.pollIntervalMs ?? DEFAULT_POLL_MS;

  const [envelope, setEnvelope] = React.useState<DataQualityEnvelope | null>(
    null,
  );
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const data = await fetchJson<DataQualityEnvelope>(
          "/api/data-quality",
        );
        if (cancelled) return;
        setEnvelope(data);
        setError(null);
      } catch (err) {
        if (cancelled) return;
        setError(
          err instanceof ApiError
            ? err.detail ?? err.message
            : "Could not load data-quality envelope.",
        );
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    const id = window.setInterval(load, pollIntervalMs);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [pollIntervalMs]);

  const badgeMap = React.useMemo(() => {
    const map = new Map<string, FreshnessBadge>();
    for (const b of envelope?.badges ?? []) {
      map.set(b.name, b);
    }
    return map;
  }, [envelope]);

  const badge = React.useCallback(
    (name: string) => badgeMap.get(name),
    [badgeMap],
  );

  const isStale = React.useCallback(
    (name: ProviderName | string) => {
      const b = badgeMap.get(name);
      if (b) return b.tier !== "green";
      // Fallback for older API deploys without the badges block:
      // consult the per-provider status directly.
      const p = envelope?.providers.find((row) => row.name === name);
      return p ? p.status !== "green" : false;
    },
    [badgeMap, envelope],
  );

  return {
    envelope,
    badge,
    isStale,
    anyRed: Boolean(envelope?.any_red),
    staleProviders: envelope?.stale_providers ?? [],
    error,
    loading,
  };
}

export default useDataQuality;
