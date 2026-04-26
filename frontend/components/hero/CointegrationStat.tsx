"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

type Props = {
  pValue: number | null | undefined;
  halfLifeDays: number | null | undefined;
  verdict?: string | null;
  className?: string;
};

/**
 * Engle-Granger cointegration pill rendered inline on the hero card.
 * Reads the `coint_p_value` + `coint_half_life_days` fields off the
 * thesis context blob. The plain-English tooltip is the whole point —
 * a non-quant trader has to be able to glance at this and know whether
 * the snap-back trade is statistically supported.
 *
 * Visual rules:
 *   * p < 0.05  → emerald "cointegrated" (the spread is mean-reverting)
 *   * p < 0.10  → amber "weak"           (probably mean-reverting; size down)
 *   * p ≥ 0.10  → rose "decoupled"       (de-cointegrated; don't trade the spread)
 *   * NaN / null → muted "—"             (window too short / fit failed)
 *
 * The "kg of WTI per kg of Brent" hedge ratio + Johansen trace are
 * deliberately NOT surfaced here — they live in the deep-analysis view.
 */
export function CointegrationStat({
  pValue,
  halfLifeDays,
  verdict,
  className,
}: Props) {
  const finiteP =
    typeof pValue === "number" && Number.isFinite(pValue) ? pValue : null;
  const finiteHL =
    typeof halfLifeDays === "number" && Number.isFinite(halfLifeDays)
      ? halfLifeDays
      : null;

  const tone =
    finiteP === null
      ? "muted"
      : finiteP < 0.05
        ? "ok"
        : finiteP < 0.1
          ? "warn"
          : "bad";

  const toneClass = {
    ok: "border-positive/40 bg-positive/10 text-positive",
    warn: "border-warn/40 bg-warn/10 text-warn",
    bad: "border-negative/40 bg-negative/10 text-negative",
    muted: "border-border bg-bg-2 text-text-muted",
  }[tone];

  const label = (() => {
    if (finiteP === null) return "Coint —";
    const pStr =
      finiteP < 0.001 ? "<0.001" : finiteP.toFixed(3).replace(/^0/, "");
    const hlStr =
      finiteHL === null ? "" : ` (HL ${finiteHL.toFixed(1)}d)`;
    return `Coint p=${pStr}${hlStr}`;
  })();

  const verdictCopy = (() => {
    if (verdict === "cointegrated") return "Strongly mean-reverting on this window.";
    if (verdict === "weak") return "Marginally mean-reverting — size down.";
    if (verdict === "not_cointegrated")
      return "De-cointegrated — the spread is not mean-reverting right now.";
    return "Inconclusive — the window is too short to test.";
  })();

  const tooltipBody = (
    <div className="max-w-xs space-y-1.5">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-text-muted">
        Engle-Granger cointegration
      </p>
      <p>
        Tests whether Brent and WTI move together over the long run. A
        small p-value (under 0.05) means the gap between them keeps
        snapping back to a stable spread — the textbook setup for a
        mean-reversion trade.
      </p>
      <p className="text-text-secondary">{verdictCopy}</p>
      {finiteHL !== null ? (
        <p className="text-text-muted">
          Half-life: ~{finiteHL.toFixed(1)} day
          {finiteHL >= 1.5 ? "s" : ""} for the spread to close half of any
          dislocation.
        </p>
      ) : null}
    </div>
  );

  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            data-testid="cointegration-stat"
            data-tone={tone}
            tabIndex={0}
            className={cn(
              "inline-flex cursor-help items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-medium",
              toneClass,
              className,
            )}
            role="status"
            aria-label={`Cointegration ${label}, ${verdictCopy}`}
          >
            {label}
          </span>
        </TooltipTrigger>
        <TooltipContent side="bottom">{tooltipBody}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
