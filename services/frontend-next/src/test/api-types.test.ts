import { describe, it, expect } from "vitest";
import {
  DocumentSchema,
  JobStatusSchema,
  PagesResponseSchema,
  PromptsResponseSchema,
  ReasonResponseSchema,
  HealthResponseSchema,
} from "@/lib/api/types";

describe("zod schemas", () => {
  it("accepts a valid Document", () => {
    expect(DocumentSchema.parse({ doc_id: "a", filename: "b.pdf" }).filename).toBe("b.pdf");
  });

  it("rejects a JobStatus with bad status", () => {
    const res = JobStatusSchema.safeParse({ job_id: "x", status: "exploded" });
    expect(res.success).toBe(false);
  });

  it("accepts pages response with empty pages", () => {
    expect(PagesResponseSchema.parse({ doc_id: "a", pages: [] }).pages).toEqual([]);
  });

  it("accepts prompts response", () => {
    const parsed = PromptsResponseSchema.parse({
      sections: [{ id: "s1", label: "Summary", prompt: "p" }],
    });
    expect(parsed.sections).toHaveLength(1);
  });

  it("accepts a reason response", () => {
    const parsed = ReasonResponseSchema.parse({
      question: "q",
      answer: "a",
      confidence: "HIGH",
      cited_pages: [1, 3],
      think: "t",
      act: "ac",
      verify: "v",
      iterations: 1,
    });
    expect(parsed.cited_pages).toEqual([1, 3]);
  });

  it("accepts a health response with extra fields (passthrough)", () => {
    const parsed = HealthResponseSchema.parse({
      status: "ok",
      service: "reasoning",
      extra: "ignored-field",
    });
    expect(parsed.status).toBe("ok");
  });
});
