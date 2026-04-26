/**
 * SSR-safe `navigator.gpu` probe. Centralises the single legitimate
 * `as any` cast on the property — three.js + lib.dom haven't
 * normalised the WebGPU API surface yet — so consumers don't each
 * re-implement the guard with subtly different return semantics.
 */
export function hasWebGPU(): boolean {
  if (typeof navigator === "undefined") return false;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return !!(navigator as any).gpu;
}
