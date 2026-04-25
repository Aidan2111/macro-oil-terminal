"use client";

import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { Instrument } from "@/types/api";

type Props = {
  tier: 1 | 2 | 3;
  instrument: Instrument;
  stance: string;
  className?: string;
};

function accentClass(stance: string): string {
  const s = stance.toUpperCase();
  if (s === "LONG_SPREAD") return "bg-positive text-positive";
  if (s === "SHORT_SPREAD") return "bg-negative text-negative";
  return "bg-warn text-warn";
}

function tierLabel(tier: 1 | 2 | 3): string {
  if (tier === 1) return "Tier 1 · Paper";
  if (tier === 2) return "Tier 2 · ETF pair";
  return "Tier 3 · Futures";
}

/**
 * One instrument tier of the hero card. Paper/ETF/Futures all share the
 * same shape, diff only in copy + size. The "Execute in paper" CTA is
 * deliberately disabled — Sub-C's execute endpoint lands in Phase 4.
 */
export function InstrumentTile({
  tier,
  instrument,
  stance,
  className,
}: Props) {
  const accent = accentClass(stance);
  // Tolerate older / variant backend shapes — `suggested_size_pct`
  // may arrive as `suggested_pct_of_capital`, and either may be
  // missing entirely. Never let a `.toFixed` call on undefined take
  // down the entire route.
  const legacy = instrument as unknown as {
    suggested_size_pct?: number;
    suggested_pct_of_capital?: number;
    worst_case_per_unit?: string;
    rationale?: string;
    name?: string;
    symbol?: string | null;
  };
  const sizePctRaw =
    typeof legacy.suggested_size_pct === "number"
      ? legacy.suggested_size_pct
      : typeof legacy.suggested_pct_of_capital === "number"
        ? legacy.suggested_pct_of_capital
        : 0;
  const sizePct = Number.isFinite(sizePctRaw) ? sizePctRaw : 0;
  const worstCase =
    typeof legacy.worst_case_per_unit === "string" &&
    legacy.worst_case_per_unit.length > 0
      ? legacy.worst_case_per_unit
      : "—";
  const sigma1Preview =
    sizePct > 0
      ? `±$${Math.round(sizePct * 100)} per 1σ`
      : "No capital at risk";

  return (
    <Card
      data-testid="instrument-tile"
      data-tier={tier}
      className={cn("relative overflow-hidden", className)}
    >
      <div
        data-testid="instrument-tile-accent"
        aria-hidden
        className={cn("absolute left-0 right-0 top-0 h-1", accent)}
      />
      <CardHeader className="pt-5">
        <div className="flex items-baseline justify-between gap-2">
          <div>
            <div className="text-xs text-text-secondary uppercase tracking-wider">
              {tierLabel(tier)}
            </div>
            <div className="text-base font-semibold text-text-primary">
              {legacy.name ?? "Instrument"}
            </div>
          </div>
          {legacy.symbol ? (
            <div className="font-mono text-xs text-text-muted">
              {legacy.symbol}
            </div>
          ) : null}
        </div>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-text-secondary">{legacy.rationale ?? ""}</p>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
          <dt className="text-text-muted">Suggested size</dt>
          <dd className="text-right font-mono text-text-primary">
            {sizePct.toFixed(2)}%
          </dd>
          <dt className="text-text-muted">1σ P&amp;L preview</dt>
          <dd className="text-right font-mono text-text-primary">
            {sigma1Preview}
          </dd>
          <dt className="text-text-muted">Worst case</dt>
          <dd className="text-right font-mono text-text-primary">
            {worstCase}
          </dd>
        </dl>
        <Button
          type="button"
          variant="default"
          size="sm"
          disabled
          className="w-full"
          title="Paper execution wiring lands in Phase 4."
        >
          Execute in paper
        </Button>
      </CardContent>
    </Card>
  );
}
