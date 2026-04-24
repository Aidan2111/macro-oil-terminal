import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { Footer } from "@/components/common/Footer";

describe("Footer", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            sha: "abcdef1234567890",
            sha_short: "abcdef1",
            time: "2026-04-23T12:00:00Z",
            region: "westeurope",
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      ),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders v{sha_short} · {time} · {region} after mount", async () => {
    render(<Footer />);

    const badge = await screen.findByTestId("build-info");
    await waitFor(() => {
      expect(badge.textContent).toContain("vabcdef1");
    });
    expect(badge.textContent).toContain("2026-04-23T12:00:00Z");
    expect(badge.textContent).toContain("westeurope");
  });

  it("falls back to 'dev · local' when the endpoint is unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("network down");
      }),
    );

    render(<Footer />);
    const badge = await screen.findByTestId("build-info");
    expect(badge.textContent).toContain("vdev");
    expect(badge.textContent).toContain("local");
  });
});
