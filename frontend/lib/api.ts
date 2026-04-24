import { QueryClient } from "@tanstack/react-query";
import type { ApiErrorPayload } from "@/types/api";

/**
 * Base URL resolver.
 *
 * - In production the Static Web Apps config proxies /api/* to the
 *   FastAPI App Service, so an empty base (same-origin) works.
 * - In dev, next.config.mjs rewrites /api/* to localhost:8000.
 * - Override with NEXT_PUBLIC_API_URL for preview environments.
 *   NEXT_PUBLIC_API_BASE is kept as a fallback for scaffold code.
 */
export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ??
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") ??
  "";

export class ApiError extends Error {
  public readonly status: number;
  public readonly code?: string;
  public readonly detail?: string;

  constructor(status: number, message: string, detail?: string, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.code = code;
  }
}

function buildUrl(path: string): string {
  return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}

/**
 * Typed fetch wrapper. Parses JSON on success; on failure, tries to
 * read a `{ detail, code }` envelope and throws a typed `ApiError`.
 */
export async function fetchJson<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const url = buildUrl(path);
  let res: Response;
  try {
    res = await fetch(url, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.headers ?? {}),
      },
    });
  } catch (err) {
    throw new ApiError(0, `Network error calling ${path}`, String(err));
  }

  if (!res.ok) {
    let detail: string | undefined;
    let code: string | undefined;
    try {
      const payload = (await res.json()) as ApiErrorPayload;
      detail = payload?.detail;
      code = payload?.code;
    } catch {
      // body wasn't JSON — fall back to status text.
    }
    throw new ApiError(
      res.status,
      `Request ${path} failed with ${res.status}`,
      detail,
      code,
    );
  }

  return (await res.json()) as T;
}

export type SseEvent = {
  event: string;
  data: string;
};

/**
 * POST a body and stream SSE events back as an async generator.
 * EventSource only speaks GET and can't carry a body, so we hand-parse
 * the `text/event-stream` chunks. Caller drives the loop:
 *
 *   for await (const evt of postEventSource("/api/thesis/stream", body)) {
 *     if (evt.event === "token") { ... }
 *   }
 */
export async function* postEventSource(
  path: string,
  body: unknown,
  init?: Omit<RequestInit, "method" | "body">,
): AsyncGenerator<SseEvent, void, void> {
  const url = buildUrl(path);
  const res = await fetch(url, {
    ...init,
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...(init?.headers ?? {}),
    },
    body: JSON.stringify(body),
  });

  if (!res.ok || !res.body) {
    throw new ApiError(
      res.status,
      `Stream ${path} failed with ${res.status}`,
    );
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let blockEnd: number;
    while ((blockEnd = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, blockEnd);
      buffer = buffer.slice(blockEnd + 2);
      const evt = parseBlock(block);
      if (evt) yield evt;
    }
  }

  // Flush any trailing block the server closed without a double newline.
  if (buffer.trim().length > 0) {
    const evt = parseBlock(buffer);
    if (evt) yield evt;
  }
}

function parseBlock(block: string): SseEvent | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (dataLines.length === 0) return null;
  return { event, data: dataLines.join("\n") };
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 60 * 1000,
        retry: 1,
        refetchOnWindowFocus: false,
      },
    },
  });
}
