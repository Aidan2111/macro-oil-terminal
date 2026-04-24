import * as React from "react";

type Variant = "barrel" | "chart" | "tanker" | "info";

type Props = {
  title: string;
  message?: string;
  variant?: Variant;
  cta?: { label: string; onClick: () => void };
};

/**
 * Quiet "nothing here yet" slot. Picks one of three inline SVG
 * illustrations — a stylised oil barrel, an empty chart, a tanker
 * silhouette — plus an optional CTA.
 */
export function EmptyState({
  title,
  message,
  variant = "info",
  cta,
}: Props) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-10 text-center">
      <EmptyIllustration variant={variant} />
      <div className="text-sm font-medium text-text-primary">{title}</div>
      {message ? (
        <div className="text-xs text-text-secondary max-w-md">{message}</div>
      ) : null}
      {cta ? (
        <button
          type="button"
          onClick={cta.onClick}
          className="mt-2 rounded-btn border border-border bg-bg-3 px-3 py-1.5 text-xs text-text-primary hover:border-primary"
        >
          {cta.label}
        </button>
      ) : null}
    </div>
  );
}

function EmptyIllustration({ variant }: { variant: Variant }) {
  if (variant === "barrel") return <BarrelSvg />;
  if (variant === "chart") return <EmptyChartSvg />;
  if (variant === "tanker") return <TankerSvg />;
  return <InfoSvg />;
}

function BarrelSvg() {
  return (
    <svg
      width="56"
      height="56"
      viewBox="0 0 64 64"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      aria-hidden
      className="text-text-muted"
    >
      <ellipse cx="32" cy="14" rx="18" ry="5" />
      <path d="M14 14 V50" />
      <path d="M50 14 V50" />
      <ellipse cx="32" cy="50" rx="18" ry="5" />
      <path d="M14 26 Q32 30 50 26" />
      <path d="M14 38 Q32 42 50 38" />
    </svg>
  );
}

function EmptyChartSvg() {
  return (
    <svg
      width="56"
      height="56"
      viewBox="0 0 64 64"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      aria-hidden
      className="text-text-muted"
    >
      <path d="M10 10 V54 H58" />
      <path d="M18 44 L28 34 L36 40 L48 22" strokeDasharray="3 3" />
      <circle cx="18" cy="44" r="1.5" fill="currentColor" />
      <circle cx="48" cy="22" r="1.5" fill="currentColor" />
    </svg>
  );
}

function TankerSvg() {
  return (
    <svg
      width="64"
      height="56"
      viewBox="0 0 72 56"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      aria-hidden
      className="text-text-muted"
    >
      <path d="M6 38 H60 L66 44 H10 Z" />
      <path d="M16 38 V24 H50 V38" />
      <path d="M28 24 V16 H42 V24" />
      <path d="M34 16 V10" />
      <path d="M2 48 Q10 46 18 48 T34 48 T50 48 T66 48" />
    </svg>
  );
}

function InfoSvg() {
  return (
    <svg
      width="40"
      height="40"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      aria-hidden
      className="text-text-muted"
    >
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8 V8.01" />
      <path d="M12 11 V16" />
    </svg>
  );
}
