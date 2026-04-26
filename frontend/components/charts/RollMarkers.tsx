"use client";

import * as React from "react";

/**
 * Tiny vertical dotted markers we overlay on the Brent-WTI spread
 * chart at every detected front-month roll date. Renders as plain
 * SVG so it composes inside a Recharts `<ResponsiveContainer>` via
 * the `<Customized>` slot — see the SpreadChart usage. Hovering a
 * marker reveals a "Front-month roll" tooltip.
 *
 * The component is intentionally Recharts-aware: it expects the
 * parent to pass the `xAxisMap` + `yAxisMap` slices Recharts hands
 * to its `<Customized>` component, plus the list of roll dates as
 * ISO strings. If the parent can't pass those (e.g. during static
 * export), the component renders nothing — rolls are decorative.
 */
type RollMarkersProps = {
  /** ISO date strings (YYYY-MM-DD) where rolls were detected. */
  rolls: string[];
  /** Optional Recharts injected props (xAxisMap, yAxisMap, offset). */
  xAxisMap?: Record<string, { scale: (v: string | number) => number }>;
  yAxisMap?: Record<string, { scale: (v: string | number) => number }>;
  offset?: { top?: number; height?: number };
  /** Stroke colour for the dotted line. Defaults to a muted slate. */
  stroke?: string;
};

export function RollMarkers({
  rolls,
  xAxisMap,
  yAxisMap,
  offset,
  stroke = "rgba(148, 163, 184, 0.55)",
}: RollMarkersProps) {
  if (!rolls || rolls.length === 0) return null;
  if (!xAxisMap) return null;

  const xAxis = Object.values(xAxisMap)[0];
  if (!xAxis || typeof xAxis.scale !== "function") return null;

  const top = offset?.top ?? 0;
  const height = offset?.height ?? 200;

  return (
    <g
      data-testid="roll-markers"
      role="presentation"
      aria-label="Front-month roll markers"
    >
      {rolls.map((d) => {
        const x = xAxis.scale(d);
        if (x == null || Number.isNaN(x)) return null;
        return (
          <g key={d}>
            <line
              x1={x}
              x2={x}
              y1={top}
              y2={top + height}
              stroke={stroke}
              strokeDasharray="2 3"
              strokeWidth={1}
            />
            <title>{`Front-month roll — ${d}`}</title>
          </g>
        );
      })}
    </g>
  );
}

export default RollMarkers;
