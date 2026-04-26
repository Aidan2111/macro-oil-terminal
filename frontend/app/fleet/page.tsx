"use client";

import dynamic from "next/dynamic";
import { useMemo, useState } from "react";
import { GlobeControls } from "@/components/globe/GlobeControls";
import { VesselPanel } from "@/components/globe/VesselPanel";
import type { FlagCategory, Vessel } from "@/components/globe/types";
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

/**
 * Fleet page — WebGPU-backed 3D globe, floating filter chips, right-hand
 * detail sheet. Mock vessel data until Sub-C's /api/fleet/vessels lands.
 */
export default function FleetPage() {
  const vessels = mockVessels as Vessel[];
  const [visibleCategories, setVisibleCategories] = useState<Set<FlagCategory>>(
    () => new Set<FlagCategory>(["domestic", "shadow", "sanctioned", "other"]),
  );
  const [selected, setSelected] = useState<Vessel | null>(null);

  const counts = useMemo(() => {
    const acc: Record<FlagCategory, number> = {
      domestic: 0,
      shadow: 0,
      sanctioned: 0,
      other: 0,
    };
    for (const v of vessels) acc[v.flag_category]++;
    return acc;
  }, [vessels]);

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
        <FleetGlobe
          vessels={vessels}
          visibleCategories={visibleCategories}
          onVesselClick={setSelected}
        />
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
