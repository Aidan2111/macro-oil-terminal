import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { HeroBackground } from "@/components/hero/HeroBackground";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function stubMatchMedia(matchers: Record<string, boolean>) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: matchers[query] ?? false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  );
}

describe("HeroBackground viewport gate", () => {
  it("renders the static gradient fallback on mobile (<768px)", () => {
    stubMatchMedia({
      "(min-width: 768px)": false,
      "(prefers-reduced-motion: reduce)": false,
    });
    render(<HeroBackground stretchFactor={0.5} className="absolute inset-0" />);
    // Mobile path must NOT mount the WebGPU canvas — the static
    // gradient div is the final state. This is the load-bearing
    // assertion: if it regresses, the three.js chunk is back on the
    // mobile critical path.
    const fallback = screen.getByTestId("hero-shader-fallback");
    expect(fallback).toBeInTheDocument();
    expect(fallback).toHaveAttribute("aria-hidden");
    expect(fallback.tagName).toBe("DIV");
    expect(screen.queryByTestId("hero-shader-canvas")).toBeNull();
  });

  it("renders the static gradient fallback under prefers-reduced-motion", () => {
    stubMatchMedia({
      "(min-width: 768px)": true,
      "(prefers-reduced-motion: reduce)": true,
    });
    render(<HeroBackground stretchFactor={0} className="absolute inset-0" />);
    expect(screen.getByTestId("hero-shader-fallback")).toBeInTheDocument();
    expect(screen.queryByTestId("hero-shader-canvas")).toBeNull();
  });

  it("forwards className to the fallback element", () => {
    stubMatchMedia({ "(min-width: 768px)": false });
    render(
      <HeroBackground stretchFactor={0.2} className="opacity-40 test-class" />,
    );
    const fallback = screen.getByTestId("hero-shader-fallback");
    expect(fallback.className).toContain("opacity-40");
    expect(fallback.className).toContain("test-class");
  });
});
