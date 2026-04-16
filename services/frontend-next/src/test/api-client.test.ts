import { describe, it, expect, afterEach, vi } from "vitest";
import { z } from "zod";
import { request, ApiError } from "@/lib/api/client";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
});

function fakeFetch(payload: unknown, { status = 200, contentType = "application/json" } = {}) {
  return vi.fn(async () =>
    new Response(contentType.includes("json") ? JSON.stringify(payload) : String(payload), {
      status,
      headers: { "content-type": contentType },
    })
  );
}

describe("request()", () => {
  it("parses JSON and validates with zod schema", async () => {
    globalThis.fetch = fakeFetch({ a: 1 }) as unknown as typeof fetch;
    const result = await request("http://x/", { schema: z.object({ a: z.number() }) });
    expect(result).toEqual({ a: 1 });
  });

  it("throws ApiError when schema does not match", async () => {
    globalThis.fetch = fakeFetch({ a: "not-a-number" }) as unknown as typeof fetch;
    await expect(
      request("http://x/", { schema: z.object({ a: z.number() }) })
    ).rejects.toBeInstanceOf(ApiError);
  });

  it("throws ApiError on non-2xx responses and surfaces detail", async () => {
    globalThis.fetch = fakeFetch({ detail: "bad" }, { status: 400 }) as unknown as typeof fetch;
    await expect(request("http://x/")).rejects.toMatchObject({ status: 400, message: "bad" });
  });

  it("adds a correlation ID header automatically", async () => {
    const spy = vi.fn(async (_url, init) => {
      const h = new Headers((init as RequestInit)?.headers);
      expect(h.get("X-Request-ID")).toBeTruthy();
      return new Response("{}", { headers: { "content-type": "application/json" } });
    });
    globalThis.fetch = spy as unknown as typeof fetch;
    await request("http://x/");
    expect(spy).toHaveBeenCalled();
  });
});
