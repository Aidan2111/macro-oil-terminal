"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { normalizeStance } from "@/lib/api";
import type { Stance } from "@/types/api";

type Props = {
  /** 1..10; we clamp out-of-band values silently. */
  value: number;
  stance: string;
  className?: string;
};

/**
 * Qualitative label for a 0..10 conviction. Mirrors
 * `language.describe_confidence` in the Streamlit codebase so the copy
 * stays in sync across the two UIs.
 */
function confidenceBand(n: number): string {
  const v = Math.round(n);
  if (v <= 3) return "Low";
  if (v <= 6) return "Medium";
  if (v <= 8) return "High";
  return "Very High";
}

function stanceTint(stance: Stance): { fill: string; track: string } {
  if (stance === "LONG_SPREAD") {
    return { fill: "bg-positive", track: "bg-positive/15" };
  }
  if (stance === "SHORT_SPREAD") {
    return { fill: "bg-negative", track: "bg-negative/15" };
  }
  return { fill: "bg-warn", track: "bg-warn/15" };
}

/**
 * Custom progressbar — 10-unit track with animated fill. Uses
 * `motion.div` for a smooth initial widen on mount.
 */
export function ConfidenceBar({ value, stance, className }: Props) {
  const clamped = Math.max(0, Math.min(10, Math.round(value)));
  const band = confidenceBand(clamped);
  const pct = clamped * 10;
  const { fill, track } = stanceTint(normalizeStance(stance));

  return (
    <div className={cn("space-y-2", className)}>
      <div
        role="progressbar"
        data-testid="confidence-bar"
        data-confidence={clamped}
        aria-valuenow={clamped}
        aria-valuemin={0}
        aria-valuemax={10}
        aria-label={`Confidence ${band} (${clamped} of 10)`}
        className={cn(
          "relative h-2 w-full overflow-hidden rounded-full",
          track,
        )}
      >
        <motion.div
          data-testid="confidence-bar-fill"
          className={cn(
            "h-full rounded-full transition-[width] duration-500 ease-out",
            fill,
          )}
          // We set width via style so jsdom reads it synchronously (no
          // RAF + no framer-motion intermediate `0%`). Still wrap in
          // `motion.div` so downstream motion coordination (e.g. a
          // parent `layoutGroup`) can target the element.
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="text-xs text-text-secondary">
        Confidence: {band} ({clamped}/10)
      </div>
    </div>
  );
}
