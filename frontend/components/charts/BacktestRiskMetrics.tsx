"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { BacktestLiveResponse } from "@/types/api";

type Props = {
  data: BacktestLiveResponse | null | undefined;
  className?: string;
};

type Cell = {
  key: keyof BacktestLiveResponse | "es_975";
  label: string;
  value: number | null | undefined;
  format: (n: number) => string;
  tooltipTitle: string;
  tooltipBody: React.ReactNode;
};

function fmtRatio(n: number): string {
  if (!Number.isFinite(n)) return "—";
  return n.toFixed(2);
}

function fmtUsd(n: number): string {
  if (!Number.isFinite(n)) return "—";
  // VaR/ES are typically negative — preserve the sign for the read.
  const abs = Math.abs(n);
  const compact =
    abs >= 1e6
      ? `${(abs / 1e6).toFixed(1)}M`
      : abs >= 1e3
        ? `${(abs / 1e3).toFixed(1)}K`
        : `${abs.toFixed(0)}`;
  return n < 0 ? `−$${compact}` : `$${compact}`;
}

/**
 * Compact 4-up risk-metrics strip extending the existing Sharpe/MaxDD
 * stats row on the backtest tile. Each cell has a hover-explainable
 * definition so a non-quant user can read it without leaving the page.
 *
 * Surfaced metrics (all already computed by
 * `quantitative_models.backtest_zscore_meanreversion`):
 *   * Sortino — downside-only Sharpe; rewards upside-asymmetric strats
 *   * Calmar — annual return / |max drawdown|; punishes deep DDs
 *   * VaR-95 — historical 95% Value-at-Risk on per-trade PnL
 *   * ES-97.5 — Expected Shortfall at 97.5% (avg loss in worst 2.5%)
 *
 * VaR-95 + ES-97.5 jump deliberately — VaR sets the line, ES tells
 * you how bad the average breach is, and 97.5 is the desk-grade
 * tail confidence the brief specifically called out.
 */
export function BacktestRiskMetrics({ data, className }: Props) {
  const cells: Cell[] = [
    {
      key: "sortino",
      label: "Sortino",
      value: data?.sortino ?? null,
      format: fmtRatio,
      tooltipTitle: "Sortino ratio",
      tooltipBody: (
        <p>
          Like Sharpe, but the denominator is the stdev of <em>losing</em>
          {" "}trades only. Strategies with chunky upside but tame downside
          read higher on Sortino than Sharpe.
        </p>
      ),
    },
    {
      key: "calmar",
      label: "Calmar",
      value: data?.calmar ?? null,
      format: fmtRatio,
      tooltipTitle: "Calmar ratio",
      tooltipBody: (
        <p>
          Annualised return divided by the absolute value of the worst
          peak-to-trough drawdown. A direct read on &ldquo;how much pain
          do I have to sit through to capture this return?&rdquo;
        </p>
      ),
    },
    {
      key: "var_95",
      label: "VaR-95",
      value: data?.var_95 ?? null,
      format: fmtUsd,
      tooltipTitle: "VaR-95",
      tooltipBody: (
        <p>
          Historical 95% Value-at-Risk on per-trade PnL: the loss that
          only the worst 5% of trades exceed. A floor for &ldquo;how bad
          is a normal bad day.&rdquo;
        </p>
      ),
    },
    {
      key: "es_975",
      label: "ES-97.5",
      value: data?.es_975 ?? null,
      format: fmtUsd,
      tooltipTitle: "Expected Shortfall (97.5%)",
      tooltipBody: (
        <p>
          The average loss across the worst 2.5% of trades — i.e. the
          expected pain when VaR <em>is</em> breached. Captures fat-tail
          risk that VaR alone misses.
        </p>
      ),
    },
  ];

  return (
    <TooltipProvider delayDuration={150}>
    <div
      data-testid="backtest-risk-metrics"
      role="group"
      aria-label="Risk metrics"
      className={cn(
        "mt-3 grid grid-cols-2 gap-2 rounded-lg border border-border bg-bg-2/50 p-3 sm:grid-cols-4",
        className,
      )}
    >
      {cells.map((c) => {
        const valueStr =
          typeof c.value === "number" && Number.isFinite(c.value)
            ? c.format(c.value)
            : "—";
        return (
          <Tooltip key={c.key as string}>
            <TooltipTrigger asChild>
              <div
                tabIndex={0}
                data-testid={`risk-metric-${c.key as string}`}
                className="cursor-help rounded-md px-2 py-1.5 outline-none ring-offset-bg-1 focus-visible:ring-2 focus-visible:ring-info"
                aria-label={`${c.tooltipTitle}: ${valueStr}`}
              >
                <div className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">
                  {c.label}
                </div>
                <div className="font-mono text-sm text-text-primary">
                  {valueStr}
                </div>
              </div>
            </TooltipTrigger>
            <TooltipContent side="top">
              <div className="max-w-xs space-y-1.5">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-text-muted">
                  {c.tooltipTitle}
                </p>
                {c.tooltipBody}
              </div>
            </TooltipContent>
          </Tooltip>
        );
      })}
    </div>
    </TooltipProvider>
  );
}
