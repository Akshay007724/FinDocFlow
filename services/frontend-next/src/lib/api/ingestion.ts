import { z } from "zod";
import { apiBase } from "../config";
import { request } from "./client";
import { DocumentSchema, JobStatusSchema, PagesResponseSchema, type Document, type JobStatus, type Page } from "./types";

const DocsListSchema = z.object({ docs: z.array(DocumentSchema) });

export async function listDocuments(): Promise<Document[]> {
  const data = await request<{ docs: Document[] }>(`${apiBase.ingestion}/ingest/docs`, {
    schema: DocsListSchema,
  });
  return data.docs;
}

export async function uploadDocument(file: File): Promise<JobStatus> {
  const form = new FormData();
  form.append("file", file);
  return request<JobStatus>(`${apiBase.ingestion}/ingest/upload`, {
    method: "POST",
    body: form,
    schema: JobStatusSchema,
    timeoutMs: 120_000,
  });
}

export async function batchIngest(urls: string[], company?: string, filingYear?: number): Promise<JobStatus> {
  return request<JobStatus>(`${apiBase.ingestion}/ingest/batch`, {
    method: "POST",
    body: JSON.stringify({ urls, company, filing_year: filingYear }),
    schema: JobStatusSchema,
  });
}

export async function getJobStatus(jobId: string): Promise<JobStatus> {
  return request<JobStatus>(`${apiBase.ingestion}/ingest/status/${jobId}`, {
    schema: JobStatusSchema,
  });
}

export async function getPages(docId: string): Promise<Page[]> {
  const data = await request<{ doc_id: string; pages: Page[] }>(
    `${apiBase.ingestion}/ingest/pages/${docId}`,
    { schema: PagesResponseSchema, timeoutMs: 60_000 }
  );
  return data.pages;
}
