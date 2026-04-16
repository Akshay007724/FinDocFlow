"use client";

import { useQuery } from "@tanstack/react-query";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { listDocuments, getPages } from "@/lib/api/ingestion";
import { getSections, streamReason } from "@/lib/api/reasoning";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/empty-state";
import { SendHorizontal, MessageSquare, FileText, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import type { ReasoningStreamEvent } from "@/lib/api/types";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  phase?: "think" | "act" | "verify" | "done";
  cited?: number[];
  confidence?: string;
}

export default function ChatPage() {
  return (
    <Suspense fallback={null}>
      <ChatClient />
    </Suspense>
  );
}

function ChatClient() {
  const docsQ = useQuery({ queryKey: ["docs"], queryFn: listDocuments });
  const sectionsQ = useQuery({ queryKey: ["sections"], queryFn: getSections });

  const [selectedDocs, setSelectedDocs] = useState<string[]>([]);
  const [focusId, setFocusId] = useState<string>("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = useCallback(async () => {
    if (!input.trim()) return;
    if (!selectedDocs.length) {
      toast.error("Pick at least one document from the left first.");
      return;
    }
    const userMsg: Message = { id: crypto.randomUUID(), role: "user", content: input.trim() };
    const assistantMsg: Message = { id: crypto.randomUUID(), role: "assistant", content: "", phase: "think" };
    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setInput("");
    setPending(true);

    try {
      const pagesArrays = await Promise.all(selectedDocs.map((id) => getPages(id)));
      const pages = pagesArrays.flat();
      await streamReason(
        userMsg.content,
        pages,
        (ev: ReasoningStreamEvent) => {
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            if (ev.kind === "think" || ev.kind === "act" || ev.kind === "verify") {
              last.phase = ev.kind;
              last.content = (last.content ?? "") + (ev.content ?? "");
            } else if (ev.kind === "done") {
              last.phase = "done";
              last.content = ev.payload.answer;
              last.cited = ev.payload.cited_pages;
              last.confidence = ev.payload.confidence;
            } else if (ev.kind === "error") {
              last.content = `Error: ${ev.message}`;
              last.phase = "done";
            }
            return next;
          });
        }
      );
    } catch (err) {
      toast.error("Reasoning stream failed", { description: (err as Error).message });
    } finally {
      setPending(false);
    }
  }, [input, selectedDocs]);

  const onKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      void send();
    }
  };

  const docs = docsQ.data ?? [];
  const sections = sectionsQ.data ?? [];

  return (
    <div className="flex h-[calc(100dvh-8rem)] flex-col gap-4 md:flex-row">
      <aside className="md:w-72 shrink-0 flex flex-col gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Documents</CardTitle>
          </CardHeader>
          <CardContent className="max-h-60 overflow-y-auto">
            {docs.length === 0 ? (
              <p className="text-xs text-muted-foreground">Upload first in Library.</p>
            ) : (
              <div className="flex flex-col gap-1">
                {docs.map((d) => {
                  const active = selectedDocs.includes(d.doc_id);
                  return (
                    <button
                      key={d.doc_id}
                      onClick={() =>
                        setSelectedDocs((prev) =>
                          prev.includes(d.doc_id)
                            ? prev.filter((x) => x !== d.doc_id)
                            : [...prev, d.doc_id]
                        )
                      }
                      className={cn(
                        "rounded-md px-2.5 py-1.5 text-left text-xs transition-colors",
                        active
                          ? "bg-primary/15 text-primary"
                          : "text-foreground hover:bg-muted"
                      )}
                      aria-pressed={active}
                    >
                      <div className="flex items-center gap-2">
                        <FileText className="h-3 w-3" />
                        <span className="truncate">{d.filename}</span>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Analyst focus</CardTitle>
          </CardHeader>
          <CardContent>
            <select
              value={focusId}
              onChange={(e) => setFocusId(e.target.value)}
              className="w-full rounded-md border border-border bg-muted px-2 py-1.5 text-xs text-foreground"
              aria-label="Analyst focus"
            >
              <option value="">None</option>
              {sections.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
            <p className="mt-2 text-[0.65rem] text-muted-foreground">
              Applies the chosen analyst prompt scaffold to the next response.
            </p>
          </CardContent>
        </Card>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col rounded-lg border border-border bg-card">
        <div
          className="flex-1 overflow-y-auto p-5"
          aria-live="polite"
          aria-label="Chat transcript"
        >
          {messages.length === 0 ? (
            <EmptyState
              icon={MessageSquare}
              title="Ask anything"
              description="Ground your questions in the selected filings. ⌘+Enter sends."
            />
          ) : (
            <div className="flex flex-col gap-4">
              {messages.map((m) => (
                <MessageBubble key={m.id} msg={m} />
              ))}
              <div ref={bottomRef} />
            </div>
          )}
        </div>
        <div className="flex gap-2 border-t border-border bg-background/40 p-3">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKey}
            placeholder="Ask about revenue, risks, ESG, valuation… (⌘+Enter to send)"
            className="flex-1"
            aria-label="Chat message"
          />
          <Button onClick={send} disabled={pending || !input.trim()}>
            {pending ? <Loader2 className="h-4 w-4 animate-spin" /> : <SendHorizontal className="h-4 w-4" />}
          </Button>
        </div>
      </div>
    </div>
  );
}

function MessageBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === "user";
  return (
    <div className={cn("flex gap-3", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[78%] rounded-lg border px-4 py-2.5 text-sm",
          isUser
            ? "border-primary/40 bg-primary/15 text-foreground"
            : "border-border bg-muted/30 text-foreground"
        )}
      >
        {!isUser && msg.phase && msg.phase !== "done" && (
          <div className="mb-1 flex items-center gap-1.5 text-[0.65rem] uppercase tracking-widest text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" />
            {msg.phase}
          </div>
        )}
        <p className="whitespace-pre-wrap leading-relaxed">{msg.content || "…"}</p>
        {msg.cited && msg.cited.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {msg.cited.map((p) => (
              <Badge key={p} variant="outline" className="font-mono text-[0.65rem]">
                p.{p}
              </Badge>
            ))}
            {msg.confidence && (
              <Badge variant={msg.confidence === "HIGH" ? "accent" : msg.confidence === "LOW" ? "warning" : "default"} className="text-[0.65rem]">
                {msg.confidence}
              </Badge>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
