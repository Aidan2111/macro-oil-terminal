import * as React from "react";
import { cn } from "@/lib/utils";

export type StatusVariant = "live" | "degraded" | "stale" | "offline";

type Props = {
  status: StatusVariant;
  label?: string;
  className?: string;
};

const COLORS: Record<StatusVariant, string> = {
  live: "bg-emerald-500 shadow-[0_0_0_3px_rgba(16,185,129,0.15)]",
  degraded: "bg-amber-400 shadow-[0_0_0_3px_rgba(251,191,36,0.15)]",
  stale: "bg-rose-500 shadow-[0_0_0_3px_rgba(244,63,94,0.15)]",
  offline: "bg-slate-400 shadow-[0_0_0_3px_rgba(148,163,184,0.15)]",
};

const DEFAULT_LABELS: Record<StatusVariant, string> = {
  live: "Live",
  degraded: "Degraded",
  stale: "Stale",
  offline: "Offline",
};

/**
 * Small coloured dot + label for feed status. Colour mapping:
 *   live     -> emerald-500
 *   degraded -> amber-400
 *   stale    -> rose-500
 *   offline  -> slate-400
 */
export function StatusDot({ status, label, className }: Props) {
  const text = label ?? DEFAULT_LABELS[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 text-xs text-text-secondary",
        className,
      )}
    >
      <span
        aria-hidden
        className={cn("h-2 w-2 rounded-full", COLORS[status])}
      />
      <span>{text}</span>
    </span>
  );
}
