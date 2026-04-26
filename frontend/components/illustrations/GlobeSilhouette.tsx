/**
 * Stylised globe silhouette for the WebGPU-unavailable Fleet fallback.
 * Latitude / longitude lines plus a vessel pin near the equator.
 */
export function GlobeSilhouette({
  className,
  size = 96,
}: {
  className?: string;
  size?: number;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 96 96"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.2"
      aria-hidden
      className={className}
    >
      <circle cx="48" cy="48" r="38" opacity="0.7" />
      {/* Latitude lines */}
      <ellipse cx="48" cy="48" rx="38" ry="14" opacity="0.45" />
      <ellipse cx="48" cy="48" rx="38" ry="28" opacity="0.45" />
      {/* Longitudes */}
      <ellipse cx="48" cy="48" rx="14" ry="38" opacity="0.45" />
      <ellipse cx="48" cy="48" rx="28" ry="38" opacity="0.45" />
      {/* Equator emphasis */}
      <line x1="10" y1="48" x2="86" y2="48" opacity="0.55" />
      <line x1="48" y1="10" x2="48" y2="86" opacity="0.55" />
      {/* Vessel pin */}
      <circle cx="64" cy="42" r="2.2" fill="currentColor" opacity="0.9" />
    </svg>
  );
}
