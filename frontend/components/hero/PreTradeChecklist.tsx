"use client";

import { useCallback, useEffect, useState } from "react";
import { Circle, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ChecklistItem } from "@/types/api";

type Props = {
  items: ChecklistItem[];
  /** Stable thesis id — drives the localStorage key so ticks don't leak across runs. */
  thesisId: string;
  className?: string;
};

const STORAGE_KEY_PREFIX = "mot:preTradeChecklist:";

function readStored(thesisId: string): Record<string, boolean> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(`${STORAGE_KEY_PREFIX}${thesisId}`);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as unknown;
    if (parsed && typeof parsed === "object") {
      return parsed as Record<string, boolean>;
    }
  } catch {
    // corrupted payload — treat as empty, next write overwrites it.
  }
  return {};
}

function writeStored(thesisId: string, state: Record<string, boolean>): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      `${STORAGE_KEY_PREFIX}${thesisId}`,
      JSON.stringify(state),
    );
  } catch {
    // localStorage may be disabled (private browsing); non-fatal.
  }
}

/**
 * Five-item pre-trade checklist rendered beside the hero card. Auto-
 * checked items (vol regime + catalyst gap) come from the backend and
 * override any stored user state; user-toggleable items persist in
 * `localStorage` keyed on the thesis id.
 */
export function PreTradeChecklist({ items, thesisId, className }: Props) {
  const [userTicks, setUserTicks] = useState<Record<string, boolean>>({});

  // Hydrate from localStorage on mount + whenever the thesis id changes.
  useEffect(() => {
    setUserTicks(readStored(thesisId));
  }, [thesisId]);

  const toggle = useCallback(
    (key: string) => {
      setUserTicks((prev) => {
        const next = { ...prev, [key]: !prev[key] };
        writeStored(thesisId, next);
        return next;
      });
    },
    [thesisId],
  );

  // We render the container as `<div role="group">` (not `<ul>`) and
  // each row as `<div role="checkbox">` (not `<li>`). axe-core's
  // `aria-allowed-role` rule rejects `<li role="checkbox">` because
  // `checkbox` isn't a permitted override of `<li>`'s implicit
  // `listitem` role; the same constraint forces `<ul>` to contain
  // only `<li>`/script/template, which it can't if the children swap
  // roles. Lighthouse a11y was docking 4 points on `/` for this
  // pattern (Wave 4, 96 → 100).
  return (
    <div
      role="group"
      aria-label="Pre-trade checklist"
      data-testid="pre-trade-checklist"
      className={cn("space-y-2", className)}
    >
      {items.map((item) => {
        const isAuto = item.auto_check !== null && item.auto_check !== undefined;
        // Auto-checked items ignore localStorage entirely.
        const checked = isAuto
          ? Boolean(item.auto_check)
          : Boolean(userTicks[item.key]);
        const Icon = checked ? CheckCircle2 : Circle;

        return (
          <div
            key={item.key}
            data-testid={`checklist-item-${item.key}`}
            data-checked={String(checked)}
            data-auto={String(isAuto)}
            aria-checked={checked}
            role="checkbox"
            aria-disabled={isAuto}
            tabIndex={isAuto ? -1 : 0}
            onClick={isAuto ? undefined : () => toggle(item.key)}
            onKeyDown={
              isAuto
                ? undefined
                : (e) => {
                    if (e.key === " " || e.key === "Enter") {
                      e.preventDefault();
                      toggle(item.key);
                    }
                  }
            }
            className={cn(
              "flex items-start gap-2 rounded-md px-2 py-1.5 text-sm",
              !isAuto &&
                "cursor-pointer hover:bg-bg-3 focus:outline-none focus:ring-2 focus:ring-primary/50",
              isAuto && "opacity-90",
            )}
          >
            <Icon
              className={cn(
                "mt-0.5 h-4 w-4 shrink-0",
                checked ? "text-positive" : "text-text-muted",
              )}
              aria-hidden
            />
            <span className="text-text-secondary">{item.prompt}</span>
          </div>
        );
      })}
    </div>
  );
}
