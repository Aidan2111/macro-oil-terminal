/**
 * Equity-curve-going-flat illustration for the Track Record empty
 * state. A baseline at 0, a thin curve trending sideways, and a
 * "no trades yet" tick mark on the right.
 */
export function EquityCurveFlat({
  className,
  width = 180,
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
      viewBox="0 0 180 80"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className={className}
    >
      {/* Axes */}
      <path d="M14 70 H170" opacity="0.55" />
      <path d="M14 10 V70" opacity="0.55" />
      {/* Zero baseline */}
      <path d="M14 40 H170" strokeDasharray="2 4" opacity="0.3" />
      {/* Flat-ish equity curve — just barely above zero */}
      <path
        d="M16 42 L36 38 L56 41 L76 39 L96 42 L116 40 L136 41 L160 40"
        opacity="0.85"
      />
      {/* End-marker dot */}
      <circle cx="160" cy="40" r="2.2" fill="currentColor" opacity="0.9" />
      {/* Hash marks on x-axis */}
      <path d="M36 70 V73" opacity="0.4" />
      <path d="M76 70 V73" opacity="0.4" />
      <path d="M116 70 V73" opacity="0.4" />
      <path d="M156 70 V73" opacity="0.4" />
    </svg>
  );
}
