"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Suspense, useCallback, useMemo, useRef, useState } from "react";
import { listDocuments } from "@/lib/api/ingestion";
import { getSections, streamReport } from "@/lib/api/reasoning";
import { getPages } from "@/lib/api/ingestion";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/empty-state";
import { Check, Sparkles, Download, FileText, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import type { ReportStreamEvent, Page } from "@/lib/api/types";

interface SectionState {
  id: string;
  label: string;
  status: "idle" | "streaming" | "done" | "error";
  content: string;
}

export default function ReportsPage() {
  return (
    <Suspense fallback={null}>
      <ReportsClient />
    </Suspense>
  );
}

function ReportsClient() {
  const docsQ = useQuery({ queryKey: ["docs"], queryFn: listDocuments });
  const sectionsQ = useQuery({ queryKey: ["sections"], queryFn: getSections });

  const [selectedDocs, setSelectedDocs] = useState<string[]>([]);
  const [selectedSections, setSelectedSections] = useState<string[]>([]);
  const [state, setState] = useState<Record<string, SectionState>>({});
  const abortRef = useRef<AbortController | null>(null);

  const sectionsById = useMemo(() => {
    return Object.fromEntries((sectionsQ.data ?? []).map((s) => [s.id, s]));
  }, [sectionsQ.data]);

  // Default-select all sections once loaded
  if (sectionsQ.data && selectedSections.length === 0) {
    setTimeout(() => setSelectedSections(sectionsQ.data!.map((s) => s.id)), 0);
  }

  const generate = useMutation({
    mutationFn: async () => {
      if (!selectedDocs.length) throw new Error("Pick at least one document.");
      if (!selectedSections.length) throw new Error("Pick at least one section.");
      // Collect pages for all selected docs
      const pagesArrays = await Promise.all(selectedDocs.map((id) => getPages(id)));
      const pages: Page[] = pagesArrays.flat();
      // Initialize section state
      const initial: Record<string, SectionState> = {};
      for (const id of selectedSections) {
        initial[id] = { id, label: sectionsById[id]?.label ?? id, status: "idle", content: "" };
      }
      setState(initial);

      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;

      await streamReport(
        pages,
        selectedSections,
        (ev: ReportStreamEvent) => {
          if (ev.kind === "section_start") {
            setState((prev) => ({
              ...prev,
              [ev.id]: { ...(prev[ev.id] ?? { id: ev.id, label: ev.label, content: "" }), status: "streaming" },
            }));
          } else if (ev.kind === "section_token") {
            setState((prev) => ({
              ...prev,
              [ev.id]: {
                ...(prev[ev.id] ?? { id: ev.id, label: sectionsById[ev.id]?.label ?? ev.id, status: "streaming", content: "" }),
                content: (prev[ev.id]?.content ?? "") + ev.token,
                status: "streaming",
              },
            }));
          } else if (ev.kind === "section_done") {
            setState((prev) => ({
              ...prev,
              [ev.id]: {
                ...(prev[ev.id] ?? { id: ev.id, label: sectionsById[ev.id]?.label ?? ev.id, status: "done", content: "" }),
                status: "done",
                content: ev.markdown,
              },
            }));
          } else if (ev.kind === "error") {
            toast.error("Report stream failed", { description: ev.message });
          }
        },
        ctrl.signal
      );
    },
    onError: (err) => toast.error("Generation failed", { description: (err as Error).message }),
  });

  const downloadMarkdown = useCallback(() => {
    const parts: string[] = ["# FinDocFlow Analyst Report", ""];
    for (const id of selectedSections) {
      const s = state[id];
      if (!s) continue;
      parts.push(`## ${s.label}`, "", s.content, "");
    }
    const blob = new Blob([parts.join("\n")], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `findocflow-report-${Date.now()}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }, [selectedSections, state]);

  const docs = docsQ.data ?? [];
  const sections = sectionsQ.data ?? [];
  const anyDone = Object.values(state).some((s) => s.status === "done");

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight text-foreground">Report Generator</h2>
        <p className="text-sm text-muted-foreground">
          Pick documents, pick sections, stream nine analyst sections in parallel.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">1. Documents</CardTitle>
        </CardHeader>
        <CardContent>
          {docs.length === 0 ? (
            <EmptyState
              icon={FileText}
              title="No documents ingested"
              description="Head to the library and upload a filing first."
            />
          ) : (
            <div className="flex flex-wrap gap-2">
              {docs.map((d) => {
                const active = selectedDocs.includes(d.doc_id);
                return (
                  <button
                    key={d.doc_id}
                    type="button"
                    onClick={() =>
                      setSelectedDocs((prev) =>
                        prev.includes(d.doc_id)
                          ? prev.filter((x) => x !== d.doc_id)
                          : [...prev, d.doc_id]
                      )
                    }
                    className={cn(
                      "rounded-full border px-3 py-1.5 text-sm transition-colors",
                      active
                        ? "border-primary/40 bg-primary/15 text-primary"
                        : "border-border bg-muted/30 text-foreground hover:bg-muted"
                    )}
                    aria-pressed={active}
                  >
                    {d.filename}
                  </button>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">2. Sections</CardTitle>
        </CardHeader>
        <CardContent>
          {sections.length === 0 ? (
            <div className="shimmer h-14 rounded-md" />
          ) : (
            <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
              {sections.map((s) => {
                const active = selectedSections.includes(s.id);
                return (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() =>
                      setSelectedSections((prev) =>
                        prev.includes(s.id)
                          ? prev.filter((x) => x !== s.id)
                          : [...prev, s.id]
                      )
                    }
                    className={cn(
                      "flex items-center justify-between rounded-md border px-3 py-2 text-sm transition-colors",
                      active
                        ? "border-primary/40 bg-primary/10 text-primary"
                        : "border-border bg-muted/20 text-foreground hover:bg-muted"
                    )}
                    aria-pressed={active}
                  >
                    <span>{s.label}</span>
                    {active && <Check className="h-4 w-4" />}
                  </button>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center gap-3">
        <Button
          onClick={() => generate.mutate()}
          disabled={generate.isPending || !selectedDocs.length || !selectedSections.length}
          size="lg"
        >
          {generate.isPending ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" /> Streaming…
            </>
          ) : (
            <>
              <Sparkles className="h-4 w-4" /> Generate report
            </>
          )}
        </Button>
        {anyDone && (
          <Button variant="outline" onClick={downloadMarkdown}>
            <Download className="h-4 w-4" /> Download Markdown
          </Button>
        )}
      </div>

      <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {selectedSections.map((id) => {
          const s = state[id];
          const label = sectionsById[id]?.label ?? id;
          if (!s) {
            return (
              <Card key={id} className="min-h-[180px] opacity-60">
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base">{label}</CardTitle>
                    <Badge variant="outline">queued</Badge>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="shimmer h-24 rounded-md" />
                </CardContent>
              </Card>
            );
          }
          return (
            <Card key={id} className={cn("min-h-[180px]", s.status === "done" && "ring-1 ring-accent/30")}>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">{label}</CardTitle>
                  {s.status === "streaming" ? (
                    <Badge>
                      <Loader2 className="mr-1 h-3 w-3 animate-spin" /> streaming
                    </Badge>
                  ) : s.status === "done" ? (
                    <Badge variant="accent">
                      <Check className="mr-1 h-3 w-3" /> complete
                    </Badge>
                  ) : (
                    <Badge variant="outline">idle</Badge>
                  )}
                </div>
              </CardHeader>
              <CardContent>
                <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground/90">
                  {s.content || <span className="italic text-muted-foreground">Waiting…</span>}
                </p>
              </CardContent>
            </Card>
          );
        })}
      </section>
    </div>
  );
}
