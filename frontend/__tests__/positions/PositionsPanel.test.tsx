import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { PositionsView } from "@/components/positions/PositionsView";
import type { PaperAccount, PaperPosition } from "@/components/positions/types";
import positionsFixtureRaw from "@/__tests__/fixtures/positions.json";
import accountFixtureRaw from "@/__tests__/fixtures/account.json";

const positionsFixture = positionsFixtureRaw as unknown as {
  positions: PaperPosition[];
};
const accountFixture = accountFixtureRaw as unknown as PaperAccount;

/**
 * PositionsView is the client-side body of PositionsPanel. The server
 * component (PositionsPanel) only does the initial `await fetch` pair
 * and then mounts PositionsView with the result. We test the view
 * directly so we can feed fixtures + control the EventSource stub.
 */

// ---- EventSource stub --------------------------------------------------
type Listener = (evt: { data: string }) => void;
class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  listeners: Record<string, Listener[]> = {};
  onmessage: Listener | null = null;
  onerror: ((e: unknown) => void) | null = null;
  closed = false;
  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }
  addEventListener(type: string, cb: Listener) {
    (this.listeners[type] ||= []).push(cb);
  }
  removeEventListener(type: string, cb: Listener) {
    const arr = this.listeners[type];
    if (!arr) return;
    this.listeners[type] = arr.filter((x) => x !== cb);
  }
  close() {
    this.closed = true;
  }
  /** Test helper: fire a named event with the given JSON payload. */
  emit(type: string, data: unknown) {
    const payload = { data: typeof data === "string" ? data : JSON.stringify(data) };
    for (const cb of this.listeners[type] || []) cb(payload);
    if (type === "message" && this.onmessage) this.onmessage(payload);
  }
}

beforeEach(() => {
  MockEventSource.instances = [];
  vi.stubGlobal("EventSource", MockEventSource as unknown as typeof EventSource);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("PositionsView", () => {
  it("renders account summary (buying power + equity) and a row per position", () => {
    render(
      <PositionsView
        initialPositions={positionsFixture.positions}
        initialAccount={accountFixture}
      />,
    );
    expect(screen.getByTestId("positions-panel")).toBeInTheDocument();
    // Paper badge must be visible so the demo is unambiguous.
    expect(screen.getByTestId("paper-badge")).toBeInTheDocument();
    // Summary row values
    expect(screen.getByTestId("summary-buying-power").textContent).toMatch(/100,000/);
    expect(screen.getByTestId("summary-equity").textContent).toMatch(/102,500/);
    // One row per fixture position
    const rows = screen.getAllByTestId("position-row");
    expect(rows).toHaveLength(3);
    expect(rows[0].getAttribute("data-symbol")).toBe("USO");
  });

  it("renders the empty state when no positions are open", () => {
    render(
      <PositionsView
        initialPositions={[]}
        initialAccount={accountFixture}
      />,
    );
    expect(
      screen.getByText(/No open paper positions/i),
    ).toBeInTheDocument();
    expect(screen.queryAllByTestId("position-row")).toHaveLength(0);
  });

  it("quick-close POSTs the opposing side to /api/positions/execute", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({ id: "o1", status: "accepted", symbol: "USO", qty: 100, side: "sell" }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(
      <PositionsView
        initialPositions={positionsFixture.positions}
        initialAccount={accountFixture}
      />,
    );

    const closeBtn = screen.getAllByTestId("close-position")[0];
    fireEvent.click(closeBtn);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const callArgs = fetchMock.mock.calls[0] as unknown[];
    const url = callArgs[0];
    const init = callArgs[1];
    expect(url).toMatch(/\/api\/positions\/execute$/);
    const body = JSON.parse((init as RequestInit).body as string);
    // Long 100 USO → opposing sell 100 to flatten.
    expect(body).toMatchObject({
      symbol: "USO",
      qty: 100,
      side: "sell",
      type: "market",
      time_in_force: "day",
    });
    expect((init as RequestInit).method).toBe("POST");
  });

  it("updates the matching row when an SSE trade_update fires", async () => {
    render(
      <PositionsView
        initialPositions={positionsFixture.positions}
        initialAccount={accountFixture}
      />,
    );

    await waitFor(() => expect(MockEventSource.instances.length).toBe(1));
    const es = MockEventSource.instances[0];
    expect(es.url).toMatch(/\/api\/positions\/stream$/);

    // Simulate a fill that moves USO mark price to 75.00 and bumps P&L.
    act(() => {
      es.emit("trade_update", {
        event: "fill",
        order: {
          id: "o2",
          status: "filled",
          symbol: "USO",
          qty: 100,
          side: "buy",
          current_px: 75.0,
          unrealized_pnl: 450.0,
          unrealized_pnl_pct: 0.0638,
        },
      });
    });

    const usoRow = screen.getAllByTestId("position-row").find(
      (r) => r.getAttribute("data-symbol") === "USO",
    );
    expect(usoRow).toBeDefined();
    expect(usoRow!.textContent).toMatch(/75\.00/);
    expect(usoRow!.textContent).toMatch(/450/);
  });
});
