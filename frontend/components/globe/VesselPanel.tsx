"use client";

import * as React from "react";
import {
  Sheet,
  SheetContent,
} from "@/components/ui/sheet";
import type { Vessel } from "./types";
import { CATEGORY_COLORS, CATEGORY_LABELS } from "./types";

type Props = {
  vessel: Vessel | null;
  onClose: () => void;
};

function fmt(n: number | undefined, digits = 0): string {
  if (n === undefined || n === null || Number.isNaN(n)) return "—";
  return n.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

/**
 * Right-hand drawer surfacing per-vessel metadata. Migrated from a
 * hand-rolled aside to shadcn `Sheet` so we get focus trap, escape-
 * to-close, and focus return for free (review #13 axis 7).
 *
 * Visual contract is preserved like-for-like: same right-side slide,
 * same width cap, same close-on-backdrop-click. The sheet primitive's
 * built-in close button replaces the custom 44px X button — Radix
 * already enforces the 44px touch target.
 */
export function VesselPanel({ vessel, onClose }: Props) {
  const open = vessel !== null;
  return (
    <Sheet
      open={open}
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
    >
      <SheetContent
        side="right"
        aria-label="Vessel details"
        // Override the default p-6 since our content has its own
        // header + Row separators that supply padding.
        className="overflow-y-auto p-0 sm:max-w-sm"
      >
        <header className="flex items-start justify-between border-b border-border p-4 pr-12">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              {vessel ? (
                <span
                  aria-hidden
                  className="h-2.5 w-2.5 shrink-0 rounded-full"
                  style={{ background: CATEGORY_COLORS[vessel.flag_category] }}
                />
              ) : null}
              <h2 className="truncate text-sm font-semibold text-text-primary">
                {vessel?.name ?? "Vessel"}
              </h2>
            </div>
            <div className="mt-0.5 font-mono text-xs text-text-secondary">
              MMSI {vessel?.mmsi ?? "—"}
            </div>
          </div>
        </header>

        {vessel ? (
          <dl className="divide-y divide-border">
            <Row label="Category">{CATEGORY_LABELS[vessel.flag_category]}</Row>
            <Row label="Flag">{vessel.flag ?? "—"}</Row>
            <Row label="Position">
              <span className="font-mono tabular-nums">
                {vessel.lat.toFixed(3)}, {vessel.lon.toFixed(3)}
              </span>
            </Row>
            <Row label="Destination">{vessel.destination ?? "—"}</Row>
            <Row label="Cargo (bbl)">
              <span className="font-mono tabular-nums">
                {fmt(vessel.cargo_bbls)}
              </span>
            </Row>
            <Row label="ETA">
              {vessel.eta
                ? new Date(vessel.eta).toLocaleString(undefined, {
                    dateStyle: "medium",
                    timeStyle: "short",
                  })
                : "—"}
            </Row>
            <Row label="Last 24h (nm)">
              <span className="font-mono tabular-nums">
                {fmt(vessel.last_24h_nm)}
              </span>
            </Row>
          </dl>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 px-4 py-3 text-xs">
      <dt className="text-text-secondary">{label}</dt>
      <dd className="min-w-0 truncate text-right text-text-primary">{children}</dd>
    </div>
  );
}
