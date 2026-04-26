"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

type TermStructure = "contango" | "backwardation" | "flat" | null | undefined;
type VolBucket = "low" | "normal" | "high" | "unknown" | null | undefined;

type Props = {
  termStructure: TermStructure;
  volBucket: VolBucket;
  volPercentile?: number | null;
  realizedVolPct?: number | null;
  className?: string;
};

function termTone(term: TermStructure) {
  if (term === "contango") return "border-info/40 bg-info/10 text-info";
  if (term === "backwardation")
    return "border-warn/40 bg-warn/10 text-warn";
  return "border-border bg-bg-2 text-text-muted";
}

function volTone(bucket: VolBucket) {
  if (bucket === "low") return "border-positive/40 bg-positive/10 text-positive";
  if (bucket === "high") return "border-negative/40 bg-negative/10 text-negative";
  if (bucket === "normal") return "border-info/40 bg-info/10 text-info";
  return "border-border bg-bg-2 text-text-muted";
}

function termLabel(term: TermStructure): string {
  if (term === "contango") return "Contango";
  if (term === "backwardation") return "Backwardation";
  if (term === "flat") return "Flat curve";
  return "Term —";
}

function volLabel(bucket: VolBucket): string {
  if (bucket === "low") return "Low vol";
  if (bucket === "normal") return "Normal vol";
  if (bucket === "high") return "High vol";
  return "Vol —";
}

const TERM_TOOLTIP: Record<string, React.ReactNode> = {
  contango: (
    <div className="max-w-xs space-y-1.5">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-text-muted">
        Contango
      </p>
      <p>
        Front-month barrels are cheaper than barrels for later delivery.
        Storage is well-supplied and demand is loose; the curve gives
        you a tailwind for being long the back month.
      </p>
    </div>
  ),
  backwardation: (
    <div className="max-w-xs space-y-1.5">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-text-muted">
        Backwardation
      </p>
      <p>
        Front-month barrels are more expensive than later ones. The
        market is paying up for prompt supply — usually a tight-physical
        signal. Long-spread carry is negative here.
      </p>
    </div>
  ),
  flat: (
    <div className="max-w-xs space-y-1.5">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-text-muted">
        Flat curve
      </p>
      <p>
        Front and deferred barrels are priced almost identically. No
        clear directional signal from the term structure.
      </p>
    </div>
  ),
};

function volTooltip(
  bucket: VolBucket,
  pct?: number | null,
  rv?: number | null,
): React.ReactNode {
  const pctStr =
    typeof pct === "number" && Number.isFinite(pct) ? `${pct.toFixed(0)}th` : "—";
  const rvStr =
    typeof rv === "number" && Number.isFinite(rv) ? `${rv.toFixed(1)}%` : "—";
  return (
    <div className="max-w-xs space-y-1.5">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-text-muted">
        Realized vol regime
      </p>
      <p>
        20-day realized volatility on the spread sits at the {pctStr}{" "}
        percentile of the trailing year (annualised: {rvStr}).
      </p>
      {bucket === "high" ? (
        <p className="text-text-secondary">
          High-vol regime — wider stops, smaller size, and faster mean
          reversion are all on the table.
        </p>
      ) : null}
      {bucket === "low" ? (
        <p className="text-text-secondary">
          Low-vol regime — the snap-back can take longer than usual; be
          patient with the exit.
        </p>
      ) : null}
    </div>
  );
}

/**
 * Two side-by-side pills below the stance row on the hero card —
 * `[Contango]` `[Normal vol]`. Both pills are hover-explainable so a
 * trader can audit what the regime classifier said without leaving
 * the card.
 *
 * Source of truth:
 *   * `term_structure` ← `regime_service.detect_regime` ← spread sign
 *     proxy on the (Brent − WTI) front-month differential. The proxy
 *     shortcoming is documented in the service docstring; the pill's
 *     tooltip is the user-facing version of the same caveat.
 *   * `vol_bucket` ← bucketed 1y percentile of the 20-day realized
 *     vol of the spread. <33 → low, 33–66 → normal, >66 → high.
 */
export function RegimeBadges({
  termStructure,
  volBucket,
  volPercentile,
  realizedVolPct,
  className,
}: Props) {
  const termKey = (termStructure ?? "unknown") as string;
  return (
    <TooltipProvider delayDuration={150}>
    <div
      data-testid="regime-badges"
      className={cn("flex flex-wrap items-center gap-2", className)}
    >
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            data-testid="regime-term"
            data-term={termKey}
            tabIndex={0}
            role="status"
            aria-label={`Term structure: ${termLabel(termStructure)}`}
            className={cn(
              "inline-flex cursor-help items-center rounded-full border px-2.5 py-0.5 text-[11px] font-medium uppercase tracking-wider",
              termTone(termStructure),
            )}
          >
            {termLabel(termStructure)}
          </span>
        </TooltipTrigger>
        <TooltipContent side="bottom">
          {TERM_TOOLTIP[termKey] ?? (
            <p className="max-w-xs text-text-muted">
              Term structure unavailable — too few price points.
            </p>
          )}
        </TooltipContent>
      </Tooltip>

      <Tooltip>
        <TooltipTrigger asChild>
          <span
            data-testid="regime-vol"
            data-bucket={volBucket ?? "unknown"}
            tabIndex={0}
            role="status"
            aria-label={`Vol regime: ${volLabel(volBucket)}`}
            className={cn(
              "inline-flex cursor-help items-center rounded-full border px-2.5 py-0.5 text-[11px] font-medium uppercase tracking-wider",
              volTone(volBucket),
            )}
          >
            {volLabel(volBucket)}
          </span>
        </TooltipTrigger>
        <TooltipContent side="bottom">
          {volTooltip(volBucket, volPercentile, realizedVolPct)}
        </TooltipContent>
      </Tooltip>
    </div>
    </TooltipProvider>
  );
}
