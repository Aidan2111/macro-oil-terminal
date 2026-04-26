"use client";

import { useEffect, useState } from "react";
import type { HeroShaderBackground as HeroShaderBackgroundType } from "./HeroShaderBackground";

type Props = {
  /** 0 = calm cyan, 1 = turbulent crimson. Forwarded to the WebGPU shader. */
  stretchFactor: number;
  className?: string;
};

/**
 * Desktop-only shell around `HeroShaderBackground`.
 *
 * `HeroBackground` synchronously gates on `(min-width: 768px)` and
 * `(prefers-reduced-motion)` BEFORE creating the JSX node for this
 * component. As a result, on mobile this module is never referenced
 * from the live render tree — webpack still emits a separate chunk for
 * the dynamic `import()` below, but the chunk is only fetched when the
 * component actually mounts (i.e. on desktop).
 *
 * Why split this file out from `HeroBackground.tsx`: the previous
 * single-file approach had `HeroBackground.tsx` itself reference the
 * `HeroShaderBackground` type, and Next.js's bundler hoisted the chunk
 * into the page graph for both viewports. Putting the dynamic import
 * behind one extra component file means `HeroBackground.tsx` can stay
 * tiny + tree-shake-friendly, and the only path to the WebGPU/TSL
 * symbols is through this client-only module.
 */
export function HeroBackgroundDesktop({ stretchFactor, className }: Props) {
  const [Shader, setShader] = useState<typeof HeroShaderBackgroundType | null>(
    null,
  );

  useEffect(() => {
    let cancelled = false;
    void import("./HeroShaderBackground").then((mod) => {
      if (!cancelled) setShader(() => mod.HeroShaderBackground);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!Shader) return null;
  return <Shader stretchFactor={stretchFactor} className={className} />;
}
