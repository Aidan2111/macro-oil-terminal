import { cn } from "@/lib/utils";
import { normalizeStance } from "@/lib/api";
import type { Stance } from "@/types/api";

type Props = {
  stance: Stance | string;
  className?: string;
};

/**
 * Translate canonical stance to the plain-English copy we ship in
 * `language.TERMS` / `describe_stance`. Stance is already canonicalised
 * to upper-case at the call boundary via `normalizeStance()`.
 */
function stanceCopy(stance: Stance): string {
  if (stance === "LONG_SPREAD") return "Lean long";
  if (stance === "SHORT_SPREAD") return "Lean short";
  // FLAT / STAND_ASIDE → "Stand aside"
  return "Stand aside";
}

/**
 * Semantic palette token per stance — matches the shader colour choice
 * in `HeroShaderBackground` (cyan for lean long, rose for lean short,
 * amber for flat).
 */
function stanceTokens(stance: Stance): {
  container: string;
  glow: string;
  accent: string;
} {
  if (stance === "LONG_SPREAD") {
    return {
      container: "bg-positive/15 text-positive border border-positive/40",
      // CSS custom property `--stance` lets the shadow mix against the
      // current semantic colour without a cascade of variant styles.
      glow: "shadow-[0_0_20px_color-mix(in_srgb,var(--positive)_22%,transparent)]",
      accent: "positive",
    };
  }
  if (stance === "SHORT_SPREAD") {
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
 * the hero card. "Lean long / Lean short / Stand aside" matches the
 * copy the Streamlit side ships in `language.TERMS` and
 * `language.describe_stance`.
 */
export function StancePill({ stance, className }: Props) {
  const canonical = normalizeStance(stance);
  const copy = stanceCopy(canonical);
  const tokens = stanceTokens(canonical);

  return (
    <span
      data-testid="stance-pill"
      data-stance={canonical}
      data-accent={tokens.accent}
      className={cn(
        "inline-flex items-center px-4 py-2 rounded-full text-sm font-semibold uppercase tracking-wider",
        tokens.container,
        tokens.glow,
        className,
      )}
    >
      {copy}
    </span>
  );
}
