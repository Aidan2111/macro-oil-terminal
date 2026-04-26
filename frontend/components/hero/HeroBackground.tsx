"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import type { HeroShaderBackground as HeroShaderBackgroundType } from "./HeroShaderBackground";

type Props = {
  /** 0 = calm cyan, 1 = turbulent crimson. Forwarded to the WebGPU shader. */
  stretchFactor: number;
  className?: string;
};

/**
 * Viewport- and motion-gated wrapper around `HeroShaderBackground`.
 *
 * SSR / initial paint always renders the same static tokenised gradient
 * — this means the WebGPU/TSL chunk is never on the critical path.
 * After mount, on desktop (`min-width: 768px`) without
 * `prefers-reduced-motion`, we lazily `import()` `HeroShaderBackground`
 * and overlay it. On mobile (or reduced-motion, or no-WebGPU) the
 * gradient is the final state.
 *
 * Why the gate: Wave 4 Lighthouse showed home/mobile at 79 (target ≥90)
 * with the WebGPU/TSL chunk dominating TBT on mid-tier mobile. The
 * shader is decorative — opacity 0.4 noise behind the card — so we ship
 * a static gradient with the same hue palette as the fallback for
 * mobile and reduced-motion users.
 */
export function HeroBackground({ stretchFactor, className }: Props) {
  const [Shader, setShader] = useState<typeof HeroShaderBackgroundType | null>(
    null,
  );

  useEffect(() => {
    if (typeof window === "undefined") return;
    // Desktop-only gate. The matchMedia query mirrors Tailwind's `md`
    // breakpoint so the hero card's responsive padding (p-6 / md:p-8)
    // and the shader gate flip together.
    const mq = window.matchMedia("(min-width: 768px)");
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (!mq.matches || reduced.matches) return;

    let cancelled = false;
    void import("./HeroShaderBackground").then((mod) => {
      if (!cancelled) setShader(() => mod.HeroShaderBackground);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // The static gradient — cyan→amber→rose, mirroring the shader's
  // `mix(color("#22d3ee"), color("#f43f5e"), stretchU)` palette so the
  // mobile experience is visually consistent with desktop's first paint
  // before the shader hydrates. `stretchFactor` nudges the rose stop's
  // opacity so the card still reflects regime intensity.
  const stretch = Math.max(0, Math.min(1, stretchFactor));
  const fallbackStyle: React.CSSProperties = {
    backgroundImage:
      `radial-gradient(ellipse at 20% 0%, color-mix(in srgb, #22d3ee ${24 - stretch * 12}%, transparent) 0%, transparent 60%),` +
      `radial-gradient(ellipse at 80% 100%, color-mix(in srgb, #f43f5e ${10 + stretch * 22}%, transparent) 0%, transparent 60%)`,
  };

  if (Shader) {
    return <Shader stretchFactor={stretchFactor} className={className} />;
  }

  return (
    <div
      aria-hidden
      data-testid="hero-shader-fallback"
      className={cn(className)}
      style={fallbackStyle}
    />
  );
}
