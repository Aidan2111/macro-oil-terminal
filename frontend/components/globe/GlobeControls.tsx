"use client";

import { motion, useReducedMotion } from "framer-motion";
import type { FlagCategory } from "./types";
import { CATEGORY_COLORS, CATEGORY_LABELS } from "./types";

type Props = {
  visibleCategories: Set<FlagCategory>;
  onToggle: (cat: FlagCategory) => void;
  counts?: Record<FlagCategory, number>;
};

const CATS: FlagCategory[] = ["domestic", "shadow", "sanctioned", "other"];

/**
 * Floating filter chips rendered over the globe. State lives in the
 * parent so the globe gets a stable `visibleCategories` prop. Each chip
 * pulses softly when toggled so the eye registers the new visibility
 * state without needing to read the colour change.
 */
export function GlobeControls({ visibleCategories, onToggle, counts }: Props) {
  const reduced = useReducedMotion();
  return (
    <div
      role="toolbar"
      aria-label="Vessel category filters"
      className="pointer-events-auto flex flex-wrap gap-2 rounded-lg border border-border bg-bg-2/80 p-2 backdrop-blur"
    >
      {CATS.map((cat) => {
        const on = visibleCategories.has(cat);
        const count = counts?.[cat];
        return (
          <motion.button
            key={cat}
            type="button"
            onClick={() => onToggle(cat)}
            aria-pressed={on}
            // Re-mount on toggle so the pulse animation re-fires.
            // The `key` swap lets framer drive a fresh entry transition
            // each time the chip flips state.
            initial={false}
            animate={
              reduced
                ? { scale: 1 }
                : { scale: on ? [1, 1.08, 1] : [1, 0.95, 1] }
            }
            transition={{ duration: 0.3, ease: "easeOut" }}
            whileTap={reduced ? {} : { scale: 0.96 }}
            className={[
              // min-h-[44px] meets the WCAG AA / Apple HIG touch-target
              // floor; chips were 24px tall and flagged in the audit.
              "flex items-center gap-2 rounded-full px-3 py-2 min-h-[44px] text-xs font-medium transition",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-bg-1",
              on
                ? "bg-bg-3 text-text-primary"
                : "bg-transparent text-text-muted line-through opacity-60 hover:opacity-80",
            ].join(" ")}
          >
            <span
              aria-hidden
              className="h-2.5 w-2.5 rounded-full"
              style={{ background: CATEGORY_COLORS[cat] }}
            />
            {CATEGORY_LABELS[cat]}
            {typeof count === "number" ? (
              <span className="text-text-muted tabular-nums">{count}</span>
            ) : null}
          </motion.button>
        );
      })}
    </div>
  );
}
