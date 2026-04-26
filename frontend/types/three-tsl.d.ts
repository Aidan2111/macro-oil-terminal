/**
 * Project-wide type augmentation for the WebGPU + TSL stack.
 *
 * - Pulls in `@webgpu/types` (already a transitive dep of `three`),
 *   which augments the global `Navigator` interface with `gpu: GPU`.
 *   That removes the need for `(navigator as any).gpu` in
 *   `frontend/lib/has-webgpu.ts`.
 * - The per-call-site `as any` casts on TSL helpers (`dot`, `mul`,
 *   `.sub`, `.xy`, etc.) were artefacts of the destructure-cast in
 *   `FleetGlobe.tsx` widening the entire `three/tsl` namespace to
 *   `unknown`. Once that cast is gone the upstream `@types/three`
 *   signatures work as advertised, so no module declaration is
 *   needed here.
 *
 * Re-check on each `three` bump. If upstream tightens
 * `WebGPURenderer.computeAsync()` or surfaces new TSL helpers we
 * inline-cast, add the narrowest shim that lets the call site stay
 * `any`-free.
 */

/// <reference types="@webgpu/types" />

export {};
