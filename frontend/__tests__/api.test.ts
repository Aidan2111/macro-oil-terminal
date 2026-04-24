import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, fetchJson, postEventSource } from "@/lib/api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("fetchJson", () => {
  it("returns parsed JSON on 2xx", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ ok: true, count: 3 }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    const data = await fetchJson<{ ok: boolean; count: number }>(
      "/api/ping",
    );
    expect(data.ok).toBe(true);
    expect(data.count).toBe(3);
  });

  it("throws a typed ApiError with detail on 4xx/5xx", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({ detail: "no such spread", code: "NOT_FOUND" }),
          {
            status: 404,
            headers: { "content-type": "application/json" },
          },
        ),
      ),
    );

    await expect(fetchJson("/api/spread/xyz")).rejects.toMatchObject({
      name: "ApiError",
      status: 404,
      detail: "no such spread",
      code: "NOT_FOUND",
    });
  });

  it("wraps network failures in ApiError with status 0", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("fetch failed");
      }),
    );

    let caught: unknown;
    try {
      await fetchJson("/api/down");
    } catch (err) {
      caught = err;
    }
    expect(caught).toBeInstanceOf(ApiError);
    expect((caught as ApiError).status).toBe(0);
  });
});

describe("postEventSource", () => {
  it("parses SSE event/data blocks into typed events", async () => {
    const encoder = new TextEncoder();
    const chunks = [
      "event: token\ndata: hello\n\n",
      "event: token\ndata: world\n\n",
      "event: done\ndata: {}\n\n",
    ];

    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        for (const c of chunks) controller.enqueue(encoder.encode(c));
        controller.close();
      },
    });

    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(stream, {
          status: 200,
          headers: { "content-type": "text/event-stream" },
        }),
      ),
    );

    const events: { event: string; data: string }[] = [];
    for await (const evt of postEventSource("/api/stream", { foo: 1 })) {
      events.push(evt);
    }

    expect(events).toEqual([
      { event: "token", data: "hello" },
      { event: "token", data: "world" },
      { event: "done", data: "{}" },
    ]);
  });

  it("throws ApiError when the upstream returns non-2xx", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response("nope", {
          status: 500,
          headers: { "content-type": "text/plain" },
        }),
      ),
    );

    const gen = postEventSource("/api/stream", {});
    await expect(gen.next()).rejects.toBeInstanceOf(ApiError);
  });
});
