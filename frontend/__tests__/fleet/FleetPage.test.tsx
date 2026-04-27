import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

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

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function withQueryClient(ui: ReactNode) {
  // Disable retries so a mocked fetch failure resolves immediately
  // rather than retrying through the test timeout.
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>
  );
}

function mockApi({
  n_vessels = 0,
  last_message_seconds_ago = 0,
  counts = { jones_act: 0, domestic: 0, shadow: 0, sanctioned: 0 },
  total = 0,
}: {
  n_vessels?: number;
  last_message_seconds_ago?: number;
  counts?: Record<"jones_act" | "domestic" | "shadow" | "sanctioned", number>;
  total?: number;
} = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/fleet/categories")) {
        return new Response(
          JSON.stringify({
            categories: {
              jones_act: { count: counts.jones_act, vessels: [] },
              domestic: { count: counts.domestic, vessels: [] },
              shadow: { count: counts.shadow, vessels: [] },
              sanctioned: { count: counts.sanctioned, vessels: [] },
            },
            total,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (url.endsWith("/api/fleet/snapshot")) {
        return new Response(
          JSON.stringify({
            n_vessels,
            last_message_seconds_ago,
            source: "aisstream",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      throw new Error(`unmocked fetch: ${url}`);
    }),
  );
}

describe("FleetPage layout (mobile-safe sizing)", () => {
  it("uses dynamic-viewport height that accounts for ticker + bottom nav on mobile", () => {
    mockApi();
    render(withQueryClient(<FleetPage />));
    const root = screen.getByTestId("fleet-page");
    const cls = root.className;
    expect(cls).toContain("h-[calc(100dvh-10rem)]");
    expect(cls).toContain("md:h-[calc(100vh-4rem)]");
    // min-h floor matches FleetGlobe canvas's own min-h-[480px] so the
    // globe is never smaller than its useful render size.
    expect(cls).toContain("min-h-[480px]");
  });

  it("renders the globe component when the AISStream feed is healthy", async () => {
    mockApi({
      n_vessels: 12,
      last_message_seconds_ago: 5,
      counts: { jones_act: 1, domestic: 2, shadow: 3, sanctioned: 4 },
      total: 12,
    });
    render(withQueryClient(<FleetPage />));
    await waitFor(() =>
      expect(screen.getByTestId("fleet-globe-stub")).toBeInTheDocument(),
    );
    expect(
      screen.queryByTestId("fleet-feed-down-banner"),
    ).not.toBeInTheDocument();
  });
});

describe("FleetPage live data wiring (issue #67)", () => {
  it("shows the empty-feed banner when /api/fleet/snapshot reports n_vessels=0 with last_message_seconds_ago=0", async () => {
    mockApi({ n_vessels: 0, last_message_seconds_ago: 0 });
    render(withQueryClient(<FleetPage />));
    await waitFor(() =>
      expect(
        screen.getByTestId("fleet-feed-down-banner"),
      ).toBeInTheDocument(),
    );
    // Globe is replaced by the banner — no canvas painted while the
    // feed is dead.
    expect(screen.queryByTestId("fleet-globe-stub")).not.toBeInTheDocument();
  });

  it("renders chip counts from /api/fleet/categories rather than the mock fixture", async () => {
    mockApi({
      n_vessels: 7,
      last_message_seconds_ago: 3,
      counts: { jones_act: 2, domestic: 1, shadow: 2, sanctioned: 2 },
      total: 7,
    });
    render(withQueryClient(<FleetPage />));
    // Wait for the categories query to resolve and the counts to
    // render inside the chip buttons. The button labels themselves
    // appear immediately (chips render before the query resolves), so
    // we have to wait on the resolved count text.
    await waitFor(() => {
      const btn = screen.getByRole("button", { name: /Jones Act \/ Domestic/i });
      // jones_act + domestic combined = 2 + 1 = 3
      expect(btn.textContent).toMatch(/3/);
    });
    const shadowBtn = screen.getByRole("button", { name: /Shadow/i });
    expect(shadowBtn.textContent).toMatch(/2/);
    const sanctionedBtn = screen.getByRole("button", { name: /Sanctioned/i });
    expect(sanctionedBtn.textContent).toMatch(/2/);
  });
});
