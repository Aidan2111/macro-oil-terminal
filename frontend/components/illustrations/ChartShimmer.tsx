/**
 * Shimmer skeleton matching a generic chart's geometry — y-axis stub,
 * x-axis stub, and a row of pulse-animated rects standing in for
 * bars or a line trace. `animate-pulse` is a Tailwind utility from
 * the framework's default animation set, so no extra config needed.
 */
export function ChartShimmer({
  className,
  height = 280,
  bars = 16,
}: {
  className?: string;
  height?: number;
  bars?: number;
}) {
  // Pre-compute bar heights with a stable seeded pattern (rather than
  // Math.random so SSR and CSR match on hydrate).
  const heights = Array.from({ length: bars }).map(
    (_, i) => 30 + ((i * 37) % 55),
  );
  return (
    <div
      role="img"
      aria-label="Chart loading"
      className={["w-full animate-pulse", className].filter(Boolean).join(" ")}
      style={{ height }}
    >
      <svg
        width="100%"
        height="100%"
        viewBox={`0 0 400 ${height}`}
        preserveAspectRatio="none"
        fill="none"
        stroke="currentColor"
        className="text-text-muted"
      >
        {/* Axes */}
        <path d={`M40 20 V${height - 20}`} strokeWidth="1" opacity="0.4" />
        <path
          d={`M40 ${height - 20} H400`}
          strokeWidth="1"
          opacity="0.4"
        />
        {/* Bars */}
        {heights.map((h, i) => {
          const w = 16;
          const gap = 4;
          const x = 50 + i * (w + gap);
          const y = height - 20 - h;
          return (
            <rect
              key={i}
              x={x}
              y={y}
              width={w}
              height={h}
              rx={2}
              fill="currentColor"
              opacity="0.18"
            />
          );
        })}
      </svg>
    </div>
  );
}
