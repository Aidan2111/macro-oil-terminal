import { describe, it, expect } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { afterEach } from "vitest";
import { FleetGlobe } from "@/components/globe/FleetGlobe";
import type { Vessel } from "@/components/globe/types";

afterEach(() => cleanup());

const sample: Vessel[] = [
  { mmsi: "111000001", lat: 29.7, lon: -94.9, flag_category: "domestic" },
  { mmsi: "222000002", lat: 25.0, lon: 55.0, flag_category: "shadow" },
];

describe("FleetGlobe (jsdom)", () => {
  it("renders the graceful WebGPU-absent placeholder in jsdom", () => {
    // jsdom has no navigator.gpu — the component should render a
    // static placeholder rather than try to instantiate three.js.
    render(
      <FleetGlobe
        vessels={sample}
        visibleCategories={new Set(["domestic", "shadow", "sanctioned", "other"])}
        onVesselClick={() => {}}
      />,
    );
    // Placeholder carries a well-known data-testid + label
    expect(screen.getByTestId("fleet-globe-fallback")).toBeInTheDocument();
  });

  it("accepts an empty vessel list without crashing", () => {
    render(
      <FleetGlobe
        vessels={[]}
        visibleCategories={new Set(["domestic"])}
        onVesselClick={() => {}}
      />,
    );
    expect(screen.getByTestId("fleet-globe-fallback")).toBeInTheDocument();
  });
});
