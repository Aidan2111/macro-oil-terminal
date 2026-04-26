"use client";

import { X } from "lucide-react";
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
 * Right-hand sheet surfacing per-vessel metadata. Opens when `vessel`
 * is non-null. Implemented as a controlled drawer (not shadcn Sheet
 * because the scaffold has not yet wired the shadcn registry).
 */
export function VesselPanel({ vessel, onClose }: Props) {
  const open = vessel !== null;
  return (
    <>
      {/* Backdrop — click-outside to close */}
      <div
        aria-hidden
        onClick={onClose}
        className={[
          "fixed inset-0 z-30 bg-black/40 transition-opacity",
          open ? "opacity-100" : "pointer-events-none opacity-0",
        ].join(" ")}
      />

      <aside
        role="dialog"
        aria-modal="true"
        aria-label="Vessel details"
        className={[
          "fixed right-0 top-0 z-40 h-full w-full max-w-sm transform overflow-y-auto border-l border-border bg-bg-2 shadow-xl transition-transform",
          open ? "translate-x-0" : "translate-x-full",
        ].join(" ")}
      >
        <header className="flex items-start justify-between border-b border-border p-4">
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
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            // 44px floor for the touch target — flagged in the visual audit.
            className="grid place-items-center min-w-[44px] min-h-[44px] rounded-md text-text-secondary hover:bg-bg-3 hover:text-text-primary"
          >
            <X className="h-5 w-5" />
          </button>
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
      </aside>
    </>
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
