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
  /** Current rolling-std Z (the "classic" stretch — same value the hero already uses). */
  rollingZ: number | null | undefined;
  /** GARCH-normalised Z; null when the fit failed. */
  garchZ: number | null | undefined;
  /** Whether the GARCH fit succeeded. When false the toggle shows but explains the fallback. */
  garchOk: boolean | null | undefined;
  /** Reason for the fallback — surfaced in the tooltip. */
  fallbackReason?: string | null;
  className?: string;
};

const STORAGE_KEY = "mot.hero.advanced-stretch";

/**
 * Read sessionStorage *only* on the client and only after mount, so
 * the SSR-rendered output and the first client paint match (Next.js
 * hydration would otherwise warn about a mismatch).
 *
 * Cowork constraint: localStorage is unavailable in this environment.
 * sessionStorage is available and gives us the single-tab persistence
 * we actually want here — the toggle resets between tabs/windows,
 * which is the desk-trader convention anyway.
 */
function useAdvancedToggle(): [boolean, (next: boolean) => void] {
  const [on, setOn] = React.useState(false);
  React.useEffect(() => {
    try {
      const raw = window.sessionStorage.getItem(STORAGE_KEY);
      if (raw === "1") setOn(true);
    } catch {
      // Storage disabled (private mode, sandbox) — stay in-memory.
    }
  }, []);
  const setPersistent = React.useCallback((next: boolean) => {
    setOn(next);
    try {
      window.sessionStorage.setItem(STORAGE_KEY, next ? "1" : "0");
    } catch {
      // Same caveat — quietly ignore.
    }
  }, []);
  return [on, setPersistent];
}

function fmtZ(z: number | null | undefined): string {
  if (typeof z !== "number" || !Number.isFinite(z)) return "—";
  const sign = z > 0 ? "+" : z < 0 ? "−" : "";
  return `${sign}${Math.abs(z).toFixed(2)}σ`;
}

/**
 * Inline "advanced" toggle on the hero card. Off → show the classic
 * rolling-std stretch the page has always shown. On → swap in the
 * GARCH(1,1)-normalised stretch (when the fit is OK) and surface a
 * subtle badge so the user knows which stat they're looking at.
 *
 * The toggle persists to sessionStorage. The brief originally said
 * localStorage — the Cowork environment blocks localStorage, so we
 * stick with sessionStorage which is single-tab but available.
 *
 * When the GARCH fit failed (short window, divergent solver) the
 * toggle still renders but disables the "advanced" branch and the
 * tooltip shows the fallback reason so the user knows why we couldn't
 * upgrade their stretch read.
 */
export function AdvancedToggle({
  rollingZ,
  garchZ,
  garchOk,
  fallbackReason,
  className,
}: Props) {
  const [advanced, setAdvanced] = useAdvancedToggle();
  const garchUsable =
    garchOk === true &&
    typeof garchZ === "number" &&
    Number.isFinite(garchZ);
  const showGarch = advanced && garchUsable;
  const displayZ = showGarch ? garchZ : rollingZ;

  const tooltipBody = (
    <div className="max-w-xs space-y-1.5">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-text-muted">
        Stretch normalisation
      </p>
      <p>
        Rolling-std stretch divides the dislocation by the last 90 days
        of spread variability — fast and simple, but it under-counts
        vol clusters.
      </p>
      <p>
        GARCH(1,1) stretch fits a conditional-volatility model and
        divides by the model&apos;s current σ, so a high-vol regime
        compresses the stretch reading toward zero where appropriate.
      </p>
      {!garchUsable ? (
        <p className="text-warn">
          GARCH fit unavailable
          {fallbackReason ? ` — ${fallbackReason}` : ""}. Falling back to
          the rolling-std stretch.
        </p>
      ) : null}
    </div>
  );

  return (
    <TooltipProvider delayDuration={150}>
    <div
      data-testid="advanced-toggle"
      data-advanced={advanced ? "on" : "off"}
      data-garch-ok={garchUsable ? "true" : "false"}
      className={cn("flex flex-wrap items-center gap-2 text-xs", className)}
    >
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            tabIndex={0}
            data-testid="advanced-toggle-stretch-readout"
            className="inline-flex cursor-help items-center gap-1.5 rounded-md border border-border bg-bg-2 px-2 py-1 font-mono text-[11px]"
            aria-label={
              showGarch
                ? `GARCH stretch ${fmtZ(displayZ)}`
                : `Rolling stretch ${fmtZ(displayZ)}`
            }
          >
            <span className="uppercase tracking-wider text-text-muted">
              {showGarch ? "GARCH" : "Rolling"}
            </span>
            <span className="text-text-primary">{fmtZ(displayZ)}</span>
          </span>
        </TooltipTrigger>
        <TooltipContent side="bottom">{tooltipBody}</TooltipContent>
      </Tooltip>

      <button
        type="button"
        role="switch"
        aria-checked={advanced}
        aria-label="Toggle advanced GARCH-normalised stretch"
        data-testid="advanced-toggle-switch"
        onClick={() => setAdvanced(!advanced)}
        disabled={!garchUsable}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] uppercase tracking-wider transition",
          advanced && garchUsable
            ? "border-info/40 bg-info/10 text-info"
            : "border-border bg-transparent text-text-muted hover:bg-bg-2",
          !garchUsable && "cursor-not-allowed opacity-60",
        )}
      >
        <span
          aria-hidden
          className={cn(
            "h-1.5 w-1.5 rounded-full",
            advanced && garchUsable ? "bg-info" : "bg-text-muted",
          )}
        />
        Advanced
      </button>
    </div>
    </TooltipProvider>
  );
}
