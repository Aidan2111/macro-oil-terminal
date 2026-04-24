import { PositionsView } from "./PositionsView";
import type {
  PaperAccount,
  PaperPosition,
  PositionsListResponse,
} from "./types";

/**
 * Resolve the API base URL for server-side fetches.
 *
 * When Next.js runs the server component, it cannot rely on the
 * same-origin rewrite that works in the browser — the rewrite only
 * applies to the client's fetches. We prefer an explicit
 * NEXT_PUBLIC_API_URL (same var the client lib uses), fall back to
 * BACKEND_INTERNAL_URL (Azure's private loopback), and then to a
 * reasonable localhost for dev.
 */
function serverApiBase(): string {
  const explicit =
    process.env.NEXT_PUBLIC_API_URL ??
    process.env.BACKEND_INTERNAL_URL ??
    process.env.NEXT_PUBLIC_API_BASE;
  if (explicit) return explicit.replace(/\/$/, "");
  return "http://127.0.0.1:8000";
}

async function fetchJsonOrNull<T>(url: string): Promise<T | null> {
  try {
    const res = await fetch(url, {
      headers: { Accept: "application/json" },
      // Positions are inherently live state — skip Next's default
      // full-route cache so the first paint reflects reality.
      cache: "no-store",
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    // Backend may be down / not reachable during build. Render empty.
    return null;
  }
}

/**
 * Server component wrapper. Fetches the initial snapshot from
 * `/api/positions` + `/api/positions/account` and passes them down
 * to the client view, which takes over live updates via SSE.
 *
 * We never propagate backend errors to the user beyond falling back
 * to an empty list — the empty state copy ("No open paper positions")
 * carries the same message whether the account is quiet or the
 * backend is unreachable. Surfacing a 503 would leak more than it
 * clarifies for a demo-visible panel.
 */
export async function PositionsPanel() {
  const base = serverApiBase();
  const [listResp, account] = await Promise.all([
    fetchJsonOrNull<PositionsListResponse>(`${base}/api/positions`),
    fetchJsonOrNull<PaperAccount>(`${base}/api/positions/account`),
  ]);
  const positions: PaperPosition[] = listResp?.positions ?? [];
  return (
    <PositionsView initialPositions={positions} initialAccount={account} />
  );
}

export default PositionsPanel;
