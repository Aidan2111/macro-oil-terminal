"use client";

import { useMemo, useState } from "react";
import { FleetGlobe } from "@/components/globe/FleetGlobe";
import { GlobeControls } from "@/components/globe/GlobeControls";
import { VesselPanel } from "@/components/globe/VesselPanel";
import type { FlagCategory, Vessel } from "@/components/globe/types";
import mockVessels from "@/__tests__/fixtures/vessels.json";

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

  return (
    <div className="relative flex h-[calc(100vh-4rem)] w-full flex-col">
      <div className="relative flex-1">
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
