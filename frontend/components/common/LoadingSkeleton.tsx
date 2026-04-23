type Props = {
  lines?: number;
  height?: string;
  className?: string;
};

/**
 * Generic loading skeleton — a stack of `lines` shimmering bars at
 * the configured `height`. Useful while React Query is fetching.
 */
export function LoadingSkeleton({
  lines = 3,
  height = "h-4",
  className = "",
}: Props) {
  return (
    <div className={`animate-pulse space-y-2 ${className}`} aria-hidden>
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className={`rounded bg-bg-3 ${height}`}
          style={{ width: `${80 + ((i * 13) % 20)}%` }}
        />
      ))}
    </div>
  );
}
