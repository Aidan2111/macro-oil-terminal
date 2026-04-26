"use client";

import dynamic from "next/dynamic";

/**
 * Client-side wrapper for the lazy-loaded DataQualityTile.
 *
 * Next.js 15 disallows `next/dynamic({ ssr: false })` from a Server
 * Component (`app/page.tsx` is one). The fix is a thin "use client"
 * shell that owns the dynamic import — the page imports this wrapper
 * directly and the tile chunk still ships off the LCP critical path.
 */
export const DataQualityTileLazy = dynamic(
  () =>
    import("@/components/data-quality/DataQualityTile").then(
      (m) => m.DataQualityTile,
    ),
  { ssr: false },
);
