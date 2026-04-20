import { apiBase } from "../config";
import { request } from "./client";
import {
  PromptsResponseSchema,
  ReasonResponseSchema,
  type Page,
  type ReasonResponse,
  type Section,
  type ReasoningStreamEvent,
  type ReportStreamEvent,
} from "./types";
import { openSse } from "./sse";

export async function getSections(): Promise<Section[]> {
  const data = await request<{ sections: Section[] }>(`${apiBase.reasoning}/prompts`, {
    schema: PromptsResponseSchema,
  });
  return data.sections;
}

export async function reason(question: string, pages: Page[], entities: unknown[] = []): Promise<ReasonResponse> {
  return request<ReasonResponse>(`${apiBase.reasoning}/reason`, {
    method: "POST",
    body: JSON.stringify({ question, pages, entities }),
    schema: ReasonResponseSchema,
    timeoutMs: 180_000,
  });
}

export async function streamReason(
  question: string,
  pages: Page[],
  onEvent: (ev: ReasoningStreamEvent) => void,
  signal?: AbortSignal
) {
  await openSse(
    `${apiBase.reasoning}/reason/stream`,
    (msg) => {
      try {
        const parsed = JSON.parse(msg.data);
        const kind = (msg.event || "message") as ReasoningStreamEvent["kind"];
        if (kind === "think" || kind === "act" || kind === "verify") {
          onEvent({ kind, content: parsed.content ?? parsed.text ?? String(parsed) });
        } else if (kind === "done") {
          onEvent({ kind: "done", payload: parsed });
        } else if (kind === "error") {
          onEvent({ kind: "error", message: parsed.message ?? "Unknown error" });
        }
      } catch (err) {
        onEvent({ kind: "error", message: (err as Error).message });
      }
    },
    { body: { question, pages }, signal }
  );
}

export async function streamReport(
  pages: Page[],
  sectionIds: string[],
  onEvent: (ev: ReportStreamEvent) => void,
  signal?: AbortSignal
) {
  await openSse(
    `${apiBase.reasoning}/report/stream`,
    (msg) => {
      try {
        const parsed = JSON.parse(msg.data);
        const kind = (msg.event || "message") as ReportStreamEvent["kind"];
        if (kind === "section_start") {
          onEvent({ kind, id: parsed.id, label: parsed.label });
        } else if (kind === "section_token") {
          onEvent({ kind, id: parsed.id, token: parsed.token });
        } else if (kind === "section_done") {
          onEvent({ kind, id: parsed.id, markdown: parsed.markdown });
        } else if (kind === "report_done") {
          onEvent({ kind });
        } else if (kind === "error") {
          onEvent({ kind, message: parsed.message ?? "Unknown error" });
        }
      } catch (err) {
        onEvent({ kind: "error", message: (err as Error).message });
      }
    },
    { body: { pages, section_ids: sectionIds }, signal }
  );
}
