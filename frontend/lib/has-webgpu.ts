/**
 * SSR-safe `navigator.gpu` probe. Centralises the WebGPU feature-test
 * so consumers don't each re-implement the guard with subtly different
 * return semantics. The `Navigator.gpu` typing comes from
 * `@webgpu/types`, referenced by `frontend/types/three-tsl.d.ts`.
 */
export function hasWebGPU(): boolean {
  if (typeof navigator === "undefined") return false;
  return !!navigator.gpu;
}
