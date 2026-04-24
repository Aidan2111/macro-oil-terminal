"use client";

import * as React from "react";
import { fetchJson, ApiError } from "@/lib/api";
import type { BuildInfo } from "@/types/api";

/**
 * Footer: renders `v{sha_short} · {time} · {region}` from
 * /api/build-info. Fetch-on-mount with local state; the data is
 * cheap and non-blocking, so keep it off React Query to avoid
 * hydration churn on route transitions.
 */
export function Footer() {
  const [info, setInfo] = React.useState<BuildInfo | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    fetchJson<BuildInfo>("/api/build-info")
      .then((data) => {
        if (!cancelled) setInfo(data);
      })
      .catch((err: unknown) => {
        // Build info is best-effort; swallow network errors silently
        // so the footer still renders the "dev" fallback.
        if (err instanceof ApiError || err instanceof Error) return;
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const short = info?.sha_short ?? info?.sha?.slice(0, 7) ?? "dev";
  const region = info?.region ?? "local";
  const time = info?.time ?? "";

  return (
    <footer className="border-t border-border bg-bg-2 px-4 py-4 md:py-3 text-xs text-text-muted">
      <div className="mx-auto w-full max-w-5xl flex flex-col md:flex-row md:items-center gap-1 md:gap-3">
        <span className="flex-1">
          Research only. Not investment advice. Markets carry risk.
        </span>
        <span className="num" data-testid="build-info">
          v{short}
          {time ? ` · ${time}` : ""} · {region}
        </span>
      </div>
    </footer>
  );
}
