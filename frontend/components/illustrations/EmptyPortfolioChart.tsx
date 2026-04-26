/**
 * Stylised empty-portfolio chart for the Positions empty state.
 * Three faint dashed bars + an "add" plus glyph.
 */
export function EmptyPortfolioChart({
  className,
  width = 160,
  height = 96,
}: {
  className?: string;
  width?: number;
  height?: number;
}) {
  return (
    <svg
      width={width}
      height={height}
      viewBox="0 0 160 96"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinecap="round"
      aria-hidden
      className={className}
    >
      {/* Axes */}
      <path d="M14 80 H146" opacity="0.55" />
      <path d="M14 12 V80" opacity="0.55" />
      {/* Empty placeholder bars */}
      <rect
        x="32"
        y="56"
        width="18"
        height="22"
        rx="2"
        strokeDasharray="3 3"
        opacity="0.45"
      />
      <rect
        x="62"
        y="44"
        width="18"
        height="34"
        rx="2"
        strokeDasharray="3 3"
        opacity="0.45"
      />
      <rect
        x="92"
        y="60"
        width="18"
        height="18"
        rx="2"
        strokeDasharray="3 3"
        opacity="0.45"
      />
      {/* Plus glyph — "add a trade" cue */}
      <circle cx="130" cy="32" r="11" opacity="0.7" />
      <path d="M130 26 V38" opacity="0.85" />
      <path d="M124 32 H136" opacity="0.85" />
    </svg>
  );
}
