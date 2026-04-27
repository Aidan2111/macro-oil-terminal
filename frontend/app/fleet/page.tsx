"use client";

import dynamic from "next/dynamic";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { GlobeControls } from "@/components/globe/GlobeControls";
import { VesselPanel } from "@/components/globe/VesselPanel";
import type { FlagCategory, Vessel } from "@/components/globe/types";
import { fetchJson } from "@/lib/api";
import mockVessels from "@/__tests__/fixtures/vessels.json";

// FleetGlobe touches `navigator.gpu` and Three.js during mount.
// With `output: "export"` the page is pre-rendered to HTML at build
// time, but the globe's WebGPU detection diverges between server and
// client paint and triggers a React #418 hydration mismatch in
// production. Defer the globe to client-only mount.
const FleetGlobe = dynamic(
  () => import("@/components/globe/FleetGlobe").then((m) => m.FleetGlobe),
  { ssr: false, loading: () => <div className="h-full w-full" /> },
);

// API response shapes — kept narrow to what the page actually consumes.
type FleetCategoriesResponse = {
  categories: Record<
    "jones_act" | "domestic" | "shadow" | "sanctioned",
    { count: number; vessels: unknown[] }
  >;
  total: number;
};

type FleetSnapshotResponse = {
  n_vessels: number;
  last_message_seconds_ago: number;
  source: string;
};

const ZERO_COUNTS: Record<FlagCategory, number> = {
  domestic: 0,
  shadow: 0,
  sanctioned: 0,
  other: 0,
};

/**
 * Fleet page — WebGPU-backed 3D globe, floating filter chips, right-hand
 * detail sheet. Filter chip counts and the empty-feed banner come from
 * the live `/api/fleet/categories` + `/api/fleet/snapshot` endpoints.
 * Vessel SSE wiring lands separately; mockVessels remain only as a
 * visual placeholder while the AISStream feed is empty.
 */
export default function FleetPage() {
  const vessels = mockVessels as Vessel[];
  const [visibleCategories, setVisibleCategories] = useState<Set<FlagCategory>>(
    () => new Set<FlagCategory>(["domestic", "shadow", "sanctioned", "other"]),
  );
  const [selected, setSelected] = useState<Vessel | null>(null);

  // Live category counts from the backend. While the AISStream feed is
  // empty (n_vessels === 0) every count is legitimately 0 — that's the
  // truthful state, not a placeholder of 5.
  const categoriesQuery = useQuery({
    queryKey: ["fleet", "categories"],
    queryFn: () => fetchJson<FleetCategoriesResponse>("/api/fleet/categories"),
    staleTime: 30_000,
    refetchInterval: 60_000,
  });

  const snapshotQuery = useQuery({
    queryKey: ["fleet", "snapshot"],
    queryFn: () => fetchJson<FleetSnapshotResponse>("/api/fleet/snapshot"),
    staleTime: 30_000,
    refetchInterval: 60_000,
  });

  const counts = useMemo<Record<FlagCategory, number>>(() => {
    const data = categoriesQuery.data;
    if (!data) return ZERO_COUNTS;
    // The frontend chip "domestic" is the union of jones_act + domestic
    // on the API side; "other" isn't a category the API tracks, so we
    // surface it as the residual against `total` (0 when feed is empty,
    // possibly >0 once vessel ingestion is fully populated).
    const jonesAct = data.categories.jones_act?.count ?? 0;
    const apiDomestic = data.categories.domestic?.count ?? 0;
    const shadow = data.categories.shadow?.count ?? 0;
    const sanctioned = data.categories.sanctioned?.count ?? 0;
    const named = jonesAct + apiDomestic + shadow + sanctioned;
    const other = Math.max(0, (data.total ?? named) - named);
    return {
      domestic: jonesAct + apiDomestic,
      shadow,
      sanctioned,
      other,
    };
  }, [categoriesQuery.data]);

  // The AISStream feed is considered "not connected" when the backend
  // has never seen a message (n_vessels === 0 AND
  // last_message_seconds_ago === 0). When that happens we replace the
  // globe with a clear banner rather than rendering a blank canvas
  // that suggests the feed is up but empty.
  const feedDown = Boolean(
    snapshotQuery.data &&
      snapshotQuery.data.n_vessels === 0 &&
      snapshotQuery.data.last_message_seconds_ago === 0,
  );

  const toggle = (cat: FlagCategory) => {
    setVisibleCategories((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
  };

  // Mobile: the app shell stacks the ticker tape above <main> and pins a
  // fixed h-16 bottom nav, while <main> already carries pb-20 to clear
  // that nav. The previous fixed `h-[calc(100vh-4rem)]` ignored both the
  // ticker tape and the bottom nav, so on mobile the FleetPage container
  // was taller than the available main slot. Combined with the parent's
  // `overflow-hidden`, the canvas was sized off-screen behind the bottom
  // nav and the route looked broken on iPhone.
  //
  // Switch to `100dvh` (dynamic viewport unit, defined for iOS Safari
  // since 15.4) on mobile so URL-bar collapse doesn't whiplash the
  // globe height. Subtract the ~10rem of mobile chrome (ticker + bottom
  // nav + main pb-20). On md+ the desktop rail keeps the original
  // 100vh - 4rem math. `min-h-[480px]` matches FleetGlobe's own canvas
  // floor so the globe is never smaller than its useful render size.
  return (
    <div
      data-testid="fleet-page"
      className="relative flex w-full flex-col min-h-[480px] h-[calc(100dvh-10rem)] md:h-[calc(100vh-4rem)]"
    >
      <div className="relative flex-1 min-h-[480px]">
        {feedDown ? (
          <div
            data-testid="fleet-feed-down-banner"
            role="status"
            className="flex h-full w-full items-center justify-center bg-bg-1 px-6 text-center"
          >
            <div className="max-w-md space-y-2">
              <p className="text-sm font-semibold text-text-primary">
                Fleet data unavailable
              </p>
              <p className="text-xs text-text-muted">
                AISStream feed isn&apos;t connected right now — no vessel
                positions to plot. Counts above will update when the feed
                reconnects.
              </p>
            </div>
          </div>
        ) : (
          <FleetGlobe
            vessels={vessels}
            visibleCategories={visibleCategories}
            onVesselClick={setSelected}
          />
        )}
        <div className="pointer-events-none absolute left-4 top-4 z-10">
          <GlobeControls
            visibleCategories={visibleCategories}
            onToggle={toggle}
            counts={counts}
          />
        </div>
      </div>
      <VesselPanel vessel={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
