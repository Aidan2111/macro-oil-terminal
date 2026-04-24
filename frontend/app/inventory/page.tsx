"use client";

import { useQuery } from "@tanstack/react-query";
import { Section } from "@/components/common/Section";
import { LoadingSkeleton } from "@/components/common/LoadingSkeleton";
import { InventoryChart } from "@/components/charts/InventoryChart";
import { fetchJson } from "@/lib/api";
import type { InventoryLiveResponse } from "@/types/api";

export default function InventoryPage() {
  const inv = useQuery<InventoryLiveResponse>({
    queryKey: ["inventory", "page"],
    queryFn: () => fetchJson<InventoryLiveResponse>("/api/inventory"),
    staleTime: 60 * 60_000,
  });

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-2 space-y-2">
      <Section
        id="inventory"
        title="US crude inventory"
        subtitle="Weekly EIA stocks with 1-year depletion projection and Cushing overlay."
      >
        {inv.isLoading ? (
          <LoadingSkeleton lines={8} height="h-6" />
        ) : (
          <InventoryChart
            history={inv.data?.history ?? []}
            forecast={inv.data?.forecast ?? null}
            error={inv.isError ? "Inventory feed unavailable." : null}
          />
        )}
      </Section>
    </div>
  );
}
