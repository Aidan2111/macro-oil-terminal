import { TradeIdeaHeroClient } from "./TradeIdeaHeroClient";
import { API_BASE } from "@/lib/api";
import type { ThesisLatestResponse } from "@/types/api";

/**
 * Server-component wrapper. We hit `/api/thesis/latest` on the server
 * so the first paint of the route is seeded with real data; the client
 * child opens SSE for live deltas and primes the React Query cache.
 *
 * On any failure (dev preview with backend down, cold start, etc.) we
 * fall through to the client with `initialData=undefined` so its
 * loading/error branches drive the UI rather than throwing up the
 * whole route.
 */
async function fetchLatest(): Promise<ThesisLatestResponse | undefined> {
  const base = API_BASE || process.env.INTERNAL_API_URL || "";
  if (!base) {
    // No absolute URL → skip the SSR fetch (Next.js can't hit a
    // relative path from the server component). The client will do it.
    return undefined;
  }
  try {
    const res = await fetch(`${base}/api/thesis/latest`, {
      // Next.js caches fetches by default — we want fresh-on-request.
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
    if (!res.ok) return undefined;
    return (await res.json()) as ThesisLatestResponse;
  } catch {
    return undefined;
  }
}

export async function TradeIdeaHero() {
  const initial = await fetchLatest();
  return <TradeIdeaHeroClient initialData={initial} />;
}
