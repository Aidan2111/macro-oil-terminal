/**
 * Type shims for three.js WebGPU + TSL surfaces that aren't fully
 * declared upstream in three@0.169. Centralising these here keeps the
 * `as any` rash out of FleetGlobe.tsx + HeroShaderBackground.tsx.
 *
 * Re-checks needed each three.js bump — drop entries the upstream
 * .d.ts now covers. Cap this file at <60 lines so it never grows into
 * a parallel d.ts surface.
 */

import type { Vector3, Texture } from "three";

declare module "three/tsl" {
  /** Live-update handle for `uniform(float(x))` etc. The runtime sets
   *  `.value`; the .d.ts type erases it. */
  interface UniformNode {
    value: number | Vector3 | Texture | null;
  }

  /** Many TSL helpers accept arbitrary nodes/scalars; the upstream
   *  type lets only Node, but the runtime is more permissive. We
   *  widen to `unknown` so call-sites cast through unknown rather
   *  than any. */
  type TSLNodeArg = unknown;
}
