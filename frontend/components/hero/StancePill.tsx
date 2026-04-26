"use client";

import { motion, useReducedMotion } from "framer-motion";
import { cn } from "@/lib/utils";
import type { Stance } from "@/types/api";

type Props = {
  stance: Stance | string;
  className?: string;
};

/**
 * Translate any stance casing to the plain-English copy we ship in
 * `language.TERMS` / `describe_stance`. Keeping this local to the pill
 * (not a shared helper yet) so the next component that needs it pulls
 * it into `lib/language.ts` with tests at that point.
 */
function stanceCopy(stance: string): string {
  const s = stance.toUpperCase();
  if (s === "LONG_SPREAD") return "Lean long";
  if (s === "SHORT_SPREAD") return "Lean short";
  // FLAT / STAND_ASIDE / anything else → "No edge" (trader vocabulary;
  // persona 12 flagged "stand aside" as poker-tutorial phrasing).
  return "No edge";
}

/**
 * Semantic palette token per stance — matches the shader colour choice
 * in `HeroShaderBackground` (cyan for lean long, rose for lean short,
 * amber for flat).
 */
function stanceTokens(stance: string): {
  container: string;
  glow: string;
  accent: string;
} {
  const s = stance.toUpperCase();
  if (s === "LONG_SPREAD") {
    return {
      container: "bg-positive/15 text-positive border border-positive/40",
      // CSS custom property `--stance` lets the shadow mix against the
      // current semantic colour without a cascade of variant styles.
      glow: "shadow-[0_0_20px_color-mix(in_srgb,var(--positive)_22%,transparent)]",
      accent: "positive",
    };
  }
  if (s === "SHORT_SPREAD") {
    return {
      container: "bg-negative/15 text-negative border border-negative/40",
      glow: "shadow-[0_0_20px_color-mix(in_srgb,var(--negative)_22%,transparent)]",
      accent: "negative",
    };
  }
  return {
    container: "bg-warn/15 text-warn border border-warn/40",
    glow: "shadow-[0_0_20px_color-mix(in_srgb,var(--warn)_22%,transparent)]",
    accent: "warn",
  };
}

/**
 * Stance pill — the hypothetical (never imperative) verb that anchors
 * the hero card. "Lean long / Lean short / No edge" matches the copy
 * the Streamlit side ships in `language.TERMS` and
 * `language.describe_stance`. A soft scale pulse plays when the
 * `stance` prop changes so the eye catches the new state.
 */
export function StancePill({ stance, className }: Props) {
  const copy = stanceCopy(stance);
  const tokens = stanceTokens(stance);
  const reduced = useReducedMotion();

  return (
    <motion.span
      key={stance}
      data-testid="stance-pill"
      data-stance={stance}
      data-accent={tokens.accent}
      animate={
        reduced
          ? { scale: 1 }
          : { scale: [1, 1.05, 1] }
      }
      transition={{ duration: 0.4, ease: "easeOut" }}
      className={cn(
        "inline-flex items-center px-4 py-2 rounded-full text-sm font-semibold uppercase tracking-wider",
        tokens.container,
        tokens.glow,
        className,
      )}
    >
      {copy}
    </motion.span>
  );
}
