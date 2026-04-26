import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";

// next/dynamic returns a placeholder while the chunk loads in the test
// env; the FleetGlobe boot path itself is covered in FleetGlobe.test.tsx.
vi.mock("next/dynamic", () => ({
  __esModule: true,
  default: () =>
    function FleetGlobeStub() {
      return <div data-testid="fleet-globe-stub">globe</div>;
    },
}));

import FleetPage from "@/app/fleet/page";

afterEach(() => cleanup());

describe("FleetPage layout (mobile-safe sizing)", () => {
  it("uses dynamic-viewport height that accounts for ticker + bottom nav on mobile", () => {
    // Regression for the mobile fleet bug: fixed `h-[calc(100vh-4rem)]`
    // ignored the mobile ticker tape and bottom nav, so the canvas was
    // sized off-screen behind the bottom nav and looked broken on
    // iPhone. The fix uses 100dvh minus the mobile chrome on small
    // viewports while keeping the original 100vh-4rem on md+.
    render(<FleetPage />);
    const root = screen.getByTestId("fleet-page");
    const cls = root.className;
    expect(cls).toContain("h-[calc(100dvh-10rem)]");
    expect(cls).toContain("md:h-[calc(100vh-4rem)]");
    // min-h floor matches FleetGlobe canvas's own min-h-[480px] so the
    // globe is never smaller than its useful render size.
    expect(cls).toContain("min-h-[480px]");
  });

  it("renders the globe component as the page's primary content", () => {
    render(<FleetPage />);
    expect(screen.getByTestId("fleet-globe-stub")).toBeInTheDocument();
  });
});
