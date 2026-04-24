import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// Clean up the DOM after each test so queries don't bleed between cases.
afterEach(() => {
  cleanup();
});

// Polyfill matchMedia so next-themes + shadcn media queries don't blow up.
if (typeof window !== "undefined" && !window.matchMedia) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  });
}

// Recharts (and anything else relying on ResizeObserver) needs a stub
// under jsdom — without it ResponsiveContainer never measures and no
// svg is drawn. We fire the callback synchronously on observe() with a
// sensible desktop size so charts render in tests.
if (typeof window !== "undefined" && !("ResizeObserver" in window)) {
  type ROEntryLike = { contentRect: { width: number; height: number } };
  type ROCallback = (entries: ROEntryLike[]) => void;
  class ResizeObserverStub {
    callback: ROCallback;
    constructor(cb: ROCallback) {
      this.callback = cb;
    }
    observe(target: Element) {
      this.callback([
        {
          contentRect: {
            width: (target as HTMLElement).offsetWidth || 800,
            height: (target as HTMLElement).offsetHeight || 300,
          },
        },
      ]);
    }
    unobserve() {
      /* noop */
    }
    disconnect() {
      /* noop */
    }
  }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (window as any).ResizeObserver = ResizeObserverStub;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (globalThis as any).ResizeObserver = ResizeObserverStub;
}
