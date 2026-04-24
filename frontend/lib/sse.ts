import { API_BASE } from "./api";

export type SseEvent = {
  event: string;
  data: string;
};

export type SseHandlers = {
  onEvent: (evt: SseEvent) => void;
  onError?: (err: unknown) => void;
  onDone?: () => void;
  signal?: AbortSignal;
};

/**
 * Minimal POST-with-body SSE client. EventSource only supports GET;
 * we need POST for the thesis generation body, so we hand-parse
 * text/event-stream chunks.
 *
 * Fires `onEvent` for each `event: ... / data: ...` block. Calls
 * `onDone` when the stream closes cleanly, `onError` on network /
 * parse failures.
 */
export async function postEventSource(
  path: string,
  body: unknown,
  handlers: SseHandlers,
): Promise<void> {
  const url = `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(body),
    signal: handlers.signal,
  });

  if (!res.ok || !res.body) {
    handlers.onError?.(new Error(`SSE POST failed: ${res.status}`));
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let blockEnd: number;
      while ((blockEnd = buffer.indexOf("\n\n")) !== -1) {
        const block = buffer.slice(0, blockEnd);
        buffer = buffer.slice(blockEnd + 2);
        const evt = parseBlock(block);
        if (evt) handlers.onEvent(evt);
      }
    }
    handlers.onDone?.();
  } catch (err) {
    handlers.onError?.(err);
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
