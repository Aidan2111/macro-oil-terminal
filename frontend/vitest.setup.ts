import "@testing-library/jest-dom/vitest";

// jsdom does not implement WebGPU or WebGL2 in any useful form. The
// globe component is expected to detect `navigator.gpu === undefined`
// and render a graceful placeholder. No polyfills here on purpose —
// we want the jsdom path to exercise the fallback branch.
