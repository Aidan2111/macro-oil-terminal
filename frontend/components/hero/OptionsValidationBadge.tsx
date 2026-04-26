"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Small badge mounted on the trade-idea hero that surfaces whether
 * the live options chain still supports the IV / skew citation in
 * the thesis text. Three states:
 *   - valid + not stale         -> "options chain checked"      (success)
 *   - !valid, stale=true        -> "options data stale"         (warning)
 *   - !valid, stale=false       -> "options citation off"       (warning)
 *
 * If no options section was extracted, the badge renders nothing —
 * we don't want to wallpaper every thesis with "no options data".
 */
export type OptionsValidationStatus = {
  valid: boolean;
  stale?: boolean;
  message?: string | null;
  cited_iv?: number | null;
  chain_median_iv?: number | null;
};

type Props = {
  status?: OptionsValidationStatus | null;
  className?: string;
};

export function OptionsValidationBadge({ status, className }: Props) {
  if (!status) return null;
  // Pass-through "no citation" — the backend returns valid=true with
  // cited_iv=null and chain_median_iv=null. Don't render anything.
  if (status.valid && status.cited_iv == null && status.chain_median_iv == null) {
    return null;
  }

  const isOk = status.valid;
  const isStale = !isOk && status.stale === true;

  const tone = isOk
    ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-200"
    : isStale
      ? "border-amber-500/40 bg-amber-500/10 text-amber-200"
      : "border-rose-500/40 bg-rose-500/10 text-rose-200";

  const label = isOk
    ? "options chain checked"
    : isStale
      ? "options data stale"
      : "options citation off";

  const symbol = isOk ? "✓" : "⚠";

  return (
    <span
      data-testid="options-validation-badge"
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium",
        tone,
        className,
      )}
      title={status.message ?? undefined}
    >
      <span aria-hidden>{symbol}</span>
      <span>{label}</span>
    </span>
  );
}

export default OptionsValidationBadge;
