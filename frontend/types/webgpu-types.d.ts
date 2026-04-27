/**
 * Project-wide type augmentation for the WebGPU stack.
 *
 * - Pulls in `@webgpu/types` (already a transitive dep of `three`),
 *   which augments the global `Navigator` interface with `gpu: GPU`.
 *   That removes the need for `(navigator as any).gpu` in
 *   `frontend/lib/has-webgpu.ts`.
 * - TSL helpers (`dot`, `mul`, `.sub`, `.xy`, etc.) are typed by
 *   `@types/three` — no module declaration is needed here.
 *
 * Re-check on each `three` bump. If upstream tightens
 * `WebGPURenderer.computeAsync()` or surfaces new TSL helpers we
 * inline-cast, add the narrowest shim that lets the call site stay
 * `any`-free.
 */

/// <reference types="@webgpu/types" />

export {};
