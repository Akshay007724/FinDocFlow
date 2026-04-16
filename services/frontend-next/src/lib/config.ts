import { z } from "zod";

const schema = z.object({
  INGESTION_URL: z.string().url().default("http://localhost:8001"),
  EXTRACTION_URL: z.string().url().default("http://localhost:8002"),
  ENTITY_LINKING_URL: z.string().url().default("http://localhost:8003"),
  REASONING_URL: z.string().url().default("http://localhost:8004"),
});

const raw = {
  INGESTION_URL: process.env.NEXT_PUBLIC_INGESTION_URL,
  EXTRACTION_URL: process.env.NEXT_PUBLIC_EXTRACTION_URL,
  ENTITY_LINKING_URL: process.env.NEXT_PUBLIC_ENTITY_LINKING_URL,
  REASONING_URL: process.env.NEXT_PUBLIC_REASONING_URL,
};

export const config = schema.parse(raw);

// Browser-only: when hitting the proxy, use /api/* paths so CORS isn't an issue.
export const apiBase = {
  ingestion: typeof window === "undefined" ? config.INGESTION_URL : "/api/ingestion",
  extraction: typeof window === "undefined" ? config.EXTRACTION_URL : "/api/extraction",
  entityLinking: typeof window === "undefined" ? config.ENTITY_LINKING_URL : "/api/entity-linking",
  reasoning: typeof window === "undefined" ? config.REASONING_URL : "/api/reasoning",
};

export function wsUrl(path: string): string {
  if (typeof window === "undefined") return "";
  const { protocol, host } = window.location;
  const scheme = protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${host}${path}`;
}
