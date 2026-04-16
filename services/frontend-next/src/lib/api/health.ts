import { apiBase } from "../config";
import { request } from "./client";
import { HealthResponseSchema, type Health } from "./types";

export type ServiceHealth = { service: string; url: string; health?: Health; error?: string };

const services = [
  { service: "ingestion", url: `${apiBase.ingestion}/health` },
  { service: "extraction", url: `${apiBase.extraction}/health` },
  { service: "entity-linking", url: `${apiBase.entityLinking}/health` },
  { service: "reasoning", url: `${apiBase.reasoning}/health` },
] as const;

export async function checkAll(): Promise<ServiceHealth[]> {
  return Promise.all(
    services.map(async (s) => {
      try {
        const health = await request<Health>(s.url, { schema: HealthResponseSchema, timeoutMs: 5_000 });
        return { ...s, health };
      } catch (err) {
        return { ...s, error: (err as Error).message };
      }
    })
  );
}
