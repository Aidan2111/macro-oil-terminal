/**
 * Abstract spread-curves illustration for the home empty state.
 * `currentColor` based — drop into any element with a text colour
 * (typically `text-text-muted`) and the curves inherit it. Two thin
 * sine-flavoured strokes that diverge then re-converge — a literal
 * "spread" shape without leaning on any external graphic.
 */
export function SpreadCurvesIllustration({
  className,
  width = 160,
  height = 80,
}: {
  className?: string;
  width?: number;
  height?: number;
}) {
  return (
    <svg
      width={width}
      height={height}
      viewBox="0 0 160 80"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      aria-hidden
      className={className}
    >
      <path
        d="M4 56 Q24 44 44 36 T84 24 T124 28 T156 22"
        opacity="0.85"
      />
      <path
        d="M4 28 Q24 36 44 44 T84 56 T124 52 T156 58"
        opacity="0.55"
      />
      <path
        d="M4 42 H156"
        strokeDasharray="2 4"
        opacity="0.25"
      />
      <circle cx="156" cy="22" r="2" fill="currentColor" opacity="0.85" />
      <circle cx="156" cy="58" r="2" fill="currentColor" opacity="0.55" />
    </svg>
  );
}
