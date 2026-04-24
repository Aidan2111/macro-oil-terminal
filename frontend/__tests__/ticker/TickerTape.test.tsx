import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TickerTape } from "@/components/ticker/TickerTape";
import { makeSpreadFixture } from "../fixtures/spread";
import { makeInventoryFixture } from "../fixtures/inventory";

function wrap(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  );
}

describe("TickerTape", () => {
  beforeEach(() => {
    const spread = makeSpreadFixture();
    const inventory = makeInventoryFixture();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = typeof input === "string" ? input : input.toString();
        if (url.includes("/api/spread")) {
          return new Response(JSON.stringify(spread), {
            status: 200,
            headers: { "content-type": "application/json" },
          });
        }
        if (url.includes("/api/inventory")) {
          return new Response(JSON.stringify(inventory), {
            status: 200,
            headers: { "content-type": "application/json" },
          });
        }
        return new Response("", { status: 404 });
      }),
    );
    // Stub EventSource so auto-init doesn't explode.
    class MockEventSource {
      onerror: ((e: Event) => void) | null = null;
      onmessage: ((e: MessageEvent) => void) | null = null;
      close() {
        /* noop */
      }
      addEventListener() {
        /* noop */
      }
      removeEventListener() {
        /* noop */
      }
    }
    vi.stubGlobal("EventSource", MockEventSource);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders four tiles with live numbers once fetches resolve", async () => {
    wrap(<TickerTape />);

    const tape = await screen.findByTestId("ticker-tape");
    expect(tape).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getAllByRole("listitem").length).toBeGreaterThanOrEqual(4);
    });

    // Four expected symbols rendered.
    expect(screen.getAllByText(/Brent/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/WTI/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Spread/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Inventory/i).length).toBeGreaterThan(0);
  });

  it("renders an inline SVG sparkline per tile", async () => {
    const { container } = wrap(<TickerTape />);
    await screen.findByTestId("ticker-tape");
    await waitFor(() => {
      const sparks = container.querySelectorAll(
        '[data-testid="ticker-sparkline"]',
      );
      expect(sparks.length).toBeGreaterThanOrEqual(4);
    });
  });

  it("falls back to a quiet state when the API errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("boom", { status: 500 })),
    );
    wrap(<TickerTape />);
    const tape = await screen.findByTestId("ticker-tape");
    await waitFor(() => {
      expect(tape.textContent ?? "").toMatch(/unavailable|--/i);
    });
  });
});
