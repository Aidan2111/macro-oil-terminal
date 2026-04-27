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

// PositionsView mounts and immediately fires `/api/positions/account`
// + `/api/positions` to refresh the build-time snapshot (issue #68).
// The default mock returns the same fixtures the component is mounted
// with, so the dispatched snapshot_refresh is a no-op for tests that
// don't override fetch.
function defaultFetchMock(opts?: {
  positions?: PaperPosition[];
  account?: PaperAccount | null;
}) {
  const positions = opts?.positions ?? positionsFixture.positions;
  const account = opts?.account ?? accountFixture;
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/api/positions")) {
      return new Response(JSON.stringify({ positions }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }
    if (url.endsWith("/api/positions/account")) {
      return new Response(JSON.stringify(account ?? {}), {
        status: account ? 200 : 404,
        headers: { "content-type": "application/json" },
      });
    }
    throw new Error(`unmocked fetch: ${url}`);
  });
}

beforeEach(() => {
  MockEventSource.instances = [];
  vi.stubGlobal("EventSource", MockEventSource as unknown as typeof EventSource);
  vi.stubGlobal("fetch", defaultFetchMock());
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
    // The default fetch mock from beforeEach already handles
    // /api/positions and /api/positions/account refresh requests.
    // Augment it to also handle the execute POST, then assert against
    // the execute-specific call below.
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/positions")) {
        return new Response(
          JSON.stringify({ positions: positionsFixture.positions }),
          { status: 200, headers: { "content-type": "application/json" } },
        );
      }
      if (url.endsWith("/api/positions/account")) {
        return new Response(JSON.stringify(accountFixture), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      }
      if (url.endsWith("/api/positions/execute")) {
        return new Response(
          JSON.stringify({
            id: "o1",
            status: "accepted",
            symbol: "USO",
            qty: 100,
            side: "sell",
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        );
      }
      throw new Error(`unmocked fetch: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <PositionsView
        initialPositions={positionsFixture.positions}
        initialAccount={accountFixture}
      />,
    );

    const closeBtn = screen.getAllByTestId("close-position")[0];
    fireEvent.click(closeBtn);

    // The execute call should fire exactly once. Filter the mock
    // calls down to the execute URL and assert against that.
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.filter((c) =>
          String(c[0]).endsWith("/api/positions/execute"),
        ),
      ).toHaveLength(1),
    );
    const executeCall = fetchMock.mock.calls.find((c) =>
      String(c[0]).endsWith("/api/positions/execute"),
    ) as unknown[] | undefined;
    expect(executeCall).toBeDefined();
    const url = executeCall![0];
    const init = executeCall![1];
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

  it("refreshes account from the live API when the build-time snapshot is null (issue #68)", async () => {
    // The page is statically exported, so the server-component fetch
    // in PositionsPanel.tsx runs at `npm run build` time (no backend
    // reachable) and always passes initialAccount=null. The client
    // view must re-fetch on mount; otherwise tiles render $0.00 even
    // though the live Alpaca account has equity / buying power.
    render(
      <PositionsView
        initialPositions={[]}
        initialAccount={null}
      />,
    );

    // The default beforeEach fetch mock returns the fixture, which
    // has equity 102,500 and buying_power 100,000. Wait for the
    // mount-time refresh to dispatch into reducer state.
    await waitFor(() =>
      expect(screen.getByTestId("summary-equity").textContent).toMatch(
        /102,500/,
      ),
    );
    expect(screen.getByTestId("summary-buying-power").textContent).toMatch(
      /100,000/,
    );
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
