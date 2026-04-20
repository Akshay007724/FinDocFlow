import { createParser, type EventSourceMessage } from "eventsource-parser";

export interface SseOptions {
  signal?: AbortSignal;
  body?: unknown;
  headers?: Record<string, string>;
}

export async function openSse(
  url: string,
  onEvent: (ev: EventSourceMessage) => void,
  opts: SseOptions = {}
): Promise<void> {
  const headers: Record<string, string> = {
    Accept: "text/event-stream",
    "Cache-Control": "no-cache",
    "X-Request-ID": crypto.randomUUID(),
    ...(opts.headers ?? {}),
  };
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";

  const resp = await fetch(url, {
    method: opts.body !== undefined ? "POST" : "GET",
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    signal: opts.signal,
  });
  if (!resp.ok || !resp.body) {
    throw new Error(`SSE failed: ${resp.status} ${resp.statusText}`);
  }

  const parser = createParser({ onEvent });
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      parser.feed(decoder.decode(value, { stream: true }));
    }
  } finally {
    reader.releaseLock();
  }
}
