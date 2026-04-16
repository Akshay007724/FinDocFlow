import { z } from "zod";

export const DocumentSchema = z.object({
  doc_id: z.string(),
  filename: z.string(),
  format: z.string().optional(),
  total_pages: z.number().optional(),
  status: z.string().optional(),
});
export type Document = z.infer<typeof DocumentSchema>;

export const JobStatusSchema = z.object({
  job_id: z.string(),
  status: z.enum(["pending", "processing", "done", "failed", "unknown"]),
  progress: z.number().int().min(0).max(100).default(0),
  message: z.string().default(""),
  doc_ids: z.array(z.string()).default([]),
});
export type JobStatus = z.infer<typeof JobStatusSchema>;

export const PageSchema = z.object({
  page_num: z.number().int(),
  text: z.string().default(""),
  layout_type: z.string().default("text_heavy"),
  has_tables: z.boolean().default(false),
  has_images: z.boolean().default(false),
  images: z.array(z.string()).default([]),
});
export type Page = z.infer<typeof PageSchema>;

export const PagesResponseSchema = z.object({
  doc_id: z.string(),
  pages: z.array(PageSchema),
});

export const SectionSchema = z.object({
  id: z.string(),
  label: z.string(),
  icon: z.string().optional(),
  prompt: z.string(),
});
export type Section = z.infer<typeof SectionSchema>;

export const PromptsResponseSchema = z.object({
  sections: z.array(SectionSchema),
});

export const ReasonResponseSchema = z.object({
  question: z.string(),
  answer: z.string(),
  confidence: z.string(),
  cited_pages: z.array(z.number()),
  think: z.string(),
  act: z.string(),
  verify: z.string(),
  iterations: z.number().default(1),
});
export type ReasonResponse = z.infer<typeof ReasonResponseSchema>;

export const HealthResponseSchema = z
  .object({
    status: z.string(),
    service: z.string().optional(),
    model: z.string().optional(),
    ollama: z.boolean().optional(),
    neo4j: z.boolean().optional(),
  })
  .passthrough();
export type Health = z.infer<typeof HealthResponseSchema>;

// SSE reasoning events
export type ReasoningStreamEvent =
  | { kind: "think"; content: string }
  | { kind: "act"; content: string }
  | { kind: "verify"; content: string }
  | { kind: "done"; payload: ReasonResponse }
  | { kind: "error"; message: string };

// SSE report events
export type ReportStreamEvent =
  | { kind: "section_start"; id: string; label: string }
  | { kind: "section_token"; id: string; token: string }
  | { kind: "section_done"; id: string; markdown: string }
  | { kind: "report_done" }
  | { kind: "error"; message: string };
