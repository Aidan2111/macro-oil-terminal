"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchJson } from "@/lib/api";

type BuildInfo = {
  sha: string;
  sha_short?: string | null;
  time: string;
  region: string;
};

/**
 * Footer: standing disclaimer + live build-info.
 * Reads /api/build-info via React Query, displays `sha_short · region
 * · time`. No personalization (UI-polish correction applies —
 * generic product name only).
 */
export function Footer() {
  const { data } = useQuery<BuildInfo>({
    queryKey: ["build-info"],
    queryFn: () => fetchJson<BuildInfo>("/api/build-info"),
    staleTime: 5 * 60 * 1000,
  });

  const short = data?.sha_short ?? data?.sha?.slice(0, 7) ?? "dev";
  const region = data?.region ?? "local";
  const time = data?.time ?? "";

  return (
    <footer className="border-t border-border bg-bg-2 px-4 py-4 lg:py-3 text-xs text-text-muted">
      <div className="mx-auto w-full max-w-5xl flex flex-col lg:flex-row lg:items-center gap-1 lg:gap-3">
        <span className="flex-1">
          Research only. Not investment advice. Markets carry risk.
        </span>
        <span className="num">
          build {short} · {region}
          {time ? ` · ${time}` : ""}
        </span>
      </div>
    </footer>
  );
}
