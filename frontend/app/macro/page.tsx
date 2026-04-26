"use client";

import { useQuery } from "@tanstack/react-query";
import { Section } from "@/components/common/Section";
import { ChartShimmer } from "@/components/illustrations/ChartShimmer";
import { SpreadChart } from "@/components/charts/SpreadChart";
import { StretchChart } from "@/components/charts/StretchChart";
import { BacktestChart } from "@/components/charts/BacktestChart";
import { fetchJson } from "@/lib/api";
import type { BacktestLiveResponse, SpreadLiveResponse } from "@/types/api";

export default function MacroPage() {
  const spread = useQuery<SpreadLiveResponse>({
    queryKey: ["spread", "macro"],
    queryFn: () => fetchJson<SpreadLiveResponse>("/api/spread"),
    refetchInterval: 60_000,
  });

  const backtest = useQuery<BacktestLiveResponse>({
    queryKey: ["backtest", "default"],
    queryFn: () =>
      fetchJson<BacktestLiveResponse>("/api/backtest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          entry_z: 2.0,
          exit_z: 0.2,
          lookback_days: 365,
        }),
      }),
    staleTime: 5 * 60_000,
  });

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-2 space-y-2">
      <Section
        id="spread"
        title="Brent-WTI spread"
        subtitle="90-day rolling view of the arbitrage window."
      >
        {spread.isLoading ? (
          <ChartShimmer height={300} bars={20} />
        ) : (
          <SpreadChart
            data={spread.data?.history ?? []}
            error={spread.isError ? "Spread feed unavailable." : null}
          />
        )}
      </Section>

      <Section
        id="stretch"
        title="Spread stretch"
        subtitle="Rolling 90-day Z-score. Stretched beyond plus or minus 2.3 sigma."
      >
        {spread.isLoading ? (
          <ChartShimmer height={300} bars={20} />
        ) : (
          <StretchChart
            data={spread.data?.history ?? []}
            error={spread.isError ? "Stretch unavailable." : null}
          />
        )}
      </Section>

      <Section
        id="backtest"
        title="Thesis backtest"
        subtitle="How the mean-reversion model performed over the past year (walk-forward)."
      >
        {backtest.isLoading ? (
          <ChartShimmer height={320} bars={24} />
        ) : (
          <BacktestChart
            data={backtest.data ?? null}
            error={backtest.isError ? "Backtest failed." : null}
          />
        )}
      </Section>
    </div>
  );
}
