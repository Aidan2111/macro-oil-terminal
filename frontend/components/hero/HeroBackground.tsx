"use client";

import { useSyncExternalStore } from "react";
import dynamic from "next/dynamic";
import { cn } from "@/lib/utils";

type Props = {
  /** 0 = calm cyan, 1 = turbulent crimson. Forwarded to the WebGPU shader. */
  stretchFactor: number;
  className?: string;
};

/**
 * Viewport- and motion-gated wrapper around the WebGPU/TSL hero shader.
 *
 * Wave 6 rewrite: PR #20's `useEffect` matchMedia gate failed to lift
 * home/mobile Lighthouse off 71. Even though `import("./HeroShaderBackground")`
 * was guarded behind a media query, the chunk was still being parsed +
 * preloaded on mobile and the WebGPU symbols stayed on the critical
 * path. Two structural fixes here:
 *
 * 1. The matchMedia probe runs synchronously at first render via
 *    `useSyncExternalStore`, so the desktop JSX subtree is never even
 *    created on mobile (no React node ever instantiates the dynamic
 *    component, so webpack's chunk fetch never fires).
 * 2. The dynamic import target is `HeroBackgroundDesktop`, a separate
 *    file that is the *only* place referencing `HeroShaderBackground`.
 *    Combined with `next/dynamic({ ssr: false, loading: () => null })`,
 *    webpack splits the WebGPU/three.js graph into a chunk that is
 *    fetched lazily only when the desktop branch renders.
 *
 * The `output: "export"` in `next.config.mjs` rules out a true
 * server-side `userAgent()` gate (no per-request render at runtime),
 * so the gate has to be the next best thing: a synchronous client-side
 * probe that runs *before* the dynamic component is mounted.
 *
 * SSR + first paint + mobile + reduced-motion + no-WebGPU users all
 * see the static tokenised gradient defined inline below — same hue
 * palette as the shader's `mix(color("#22d3ee"), color("#f43f5e"))`.
 */

// Module-level dynamic import: webpack creates a dedicated chunk that
// only loads when this component is rendered. The fact that the
// reference exists in the module graph is fine — what matters is the
// runtime fetch, which is gated by whether the JSX node is ever
// instantiated below.
const HeroBackgroundDesktop = dynamic(
  () =>
    import("./HeroBackgroundDesktop").then((m) => m.HeroBackgroundDesktop),
  { ssr: false, loading: () => null },
);

const DESKTOP_MQ = "(min-width: 768px)";
const REDUCED_MQ = "(prefers-reduced-motion: reduce)";

function subscribe(query: string) {
  return (cb: () => void) => {
    if (typeof window === "undefined") return () => undefined;
    const mql = window.matchMedia(query);
    if (typeof mql.addEventListener === "function") {
      mql.addEventListener("change", cb);
      return () => mql.removeEventListener("change", cb);
    }
    // Safari < 14 fallback
    mql.addListener(cb);
    return () => mql.removeListener(cb);
  };
}

function getSnapshot(query: string) {
  return () => {
    if (typeof window === "undefined") return false;
    return window.matchMedia(query).matches;
  };
}

// SSR snapshot: assume mobile + reduced-motion (the conservative
// branch that never schedules the shader). This means SSR HTML always
// emits the static gradient, and on mount the client either keeps it
// (mobile / reduced-motion) or upgrades to the shader (desktop).
function getServerSnapshot() {
  return false;
}

export function HeroBackground({ stretchFactor, className }: Props) {
  const isDesktop = useSyncExternalStore(
    subscribe(DESKTOP_MQ),
    getSnapshot(DESKTOP_MQ),
    getServerSnapshot,
  );
  const reduced = useSyncExternalStore(
    subscribe(REDUCED_MQ),
    getSnapshot(REDUCED_MQ),
    getServerSnapshot,
  );

  // Static gradient — cyan→rose, mirroring the shader's palette so the
  // mobile experience is visually consistent with desktop's first paint
  // before the shader hydrates. `stretchFactor` nudges the rose stop's
  // opacity so the card still reflects regime intensity.
  const stretch = Math.max(0, Math.min(1, stretchFactor));
  const fallbackStyle: React.CSSProperties = {
    backgroundImage:
      `radial-gradient(ellipse at 20% 0%, color-mix(in srgb, #22d3ee ${24 - stretch * 12}%, transparent) 0%, transparent 60%),` +
      `radial-gradient(ellipse at 80% 100%, color-mix(in srgb, #f43f5e ${10 + stretch * 22}%, transparent) 0%, transparent 60%)`,
  };

  // CRITICAL: the desktop branch is the *only* code path that creates a
  // JSX node referencing `HeroBackgroundDesktop`. On mobile / reduced-
  // motion the branch is never taken so the dynamic chunk is never
  // requested. The static gradient is always present underneath as the
  // SSR-equivalent fallback.
  if (isDesktop && !reduced) {
    return (
      <>
        <div
          aria-hidden
          data-testid="hero-shader-fallback"
          className={cn(className)}
          style={fallbackStyle}
        />
        <HeroBackgroundDesktop
          stretchFactor={stretchFactor}
          className={className}
        />
      </>
    );
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
