import { z } from "zod";

export class ApiError extends Error {
  constructor(
    public status: number,
    public url: string,
    message: string,
    public body?: unknown
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface RequestOptions extends RequestInit {
  timeoutMs?: number;
  schema?: z.ZodType;
}

export async function request<T = unknown>(url: string, opts: RequestOptions = {}): Promise<T> {
  const { timeoutMs = 30_000, schema, ...init } = opts;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  const headers = new Headers(init.headers);
  if (!headers.has("X-Request-ID")) {
    headers.set("X-Request-ID", crypto.randomUUID());
  }
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  headers.set("Accept", headers.get("Accept") ?? "application/json");

  let resp: Response;
  try {
    resp = await fetch(url, { ...init, headers, signal: controller.signal });
  } catch (err) {
    clearTimeout(timer);
    if ((err as Error).name === "AbortError") {
      throw new ApiError(0, url, `Request timed out after ${timeoutMs}ms`);
    }
    throw new ApiError(0, url, (err as Error).message);
  }
  clearTimeout(timer);

  const contentType = resp.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json") ? await resp.json() : await resp.text();

  if (!resp.ok) {
    const detail = typeof payload === "object" && payload !== null && "detail" in payload
      ? String((payload as { detail: unknown }).detail)
      : resp.statusText;
    throw new ApiError(resp.status, url, detail, payload);
  }

  if (schema) {
    const parsed = schema.safeParse(payload);
    if (!parsed.success) {
      throw new ApiError(resp.status, url, `Contract violation: ${parsed.error.message}`, payload);
    }
    return parsed.data as T;
  }
  return payload as T;
}
