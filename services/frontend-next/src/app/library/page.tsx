"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { listDocuments } from "@/lib/api/ingestion";
import { UploadZone } from "@/components/upload-zone";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/empty-state";
import { Inbox, FileText, Search } from "lucide-react";
import { useMemo, useState } from "react";

export default function LibraryPage() {
  const qc = useQueryClient();
  const [query, setQuery] = useState("");
  const docsQ = useQuery({ queryKey: ["docs"], queryFn: listDocuments, refetchInterval: 10_000 });

  const filtered = useMemo(() => {
    const all = docsQ.data ?? [];
    if (!query) return all;
    const q = query.toLowerCase();
    return all.filter(
      (d) => d.filename.toLowerCase().includes(q) || d.doc_id.toLowerCase().includes(q)
    );
  }, [docsQ.data, query]);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight text-foreground">Document Library</h2>
        <p className="text-sm text-muted-foreground">
          Upload new filings or jump into one that&apos;s already ingested.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Upload</CardTitle>
        </CardHeader>
        <CardContent>
          <UploadZone onIngested={() => qc.invalidateQueries({ queryKey: ["docs"] })} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle className="text-base">Documents</CardTitle>
            <p className="text-xs text-muted-foreground">
              {docsQ.data ? `${docsQ.data.length} cached` : "Loading…"}
            </p>
          </div>
          <div className="relative w-64 max-w-full">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Search filename or doc id"
              className="pl-8"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label="Search documents"
            />
          </div>
        </CardHeader>
        <CardContent>
          {docsQ.isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="shimmer h-11 rounded-md" />
              ))}
            </div>
          ) : filtered.length === 0 ? (
            <EmptyState
              icon={Inbox}
              title={query ? "No matches" : "No documents yet"}
              description={
                query
                  ? "Try a different filename or clear the search."
                  : "Drop a PDF above or batch-ingest a list of SEC EDGAR URLs."
              }
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-widest text-muted-foreground">
                    <th className="px-3 py-2">Filename</th>
                    <th className="px-3 py-2">Format</th>
                    <th className="px-3 py-2">Doc ID</th>
                    <th className="px-3 py-2">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((d) => (
                    <tr key={d.doc_id} className="border-t border-border/50 hover:bg-muted/30">
                      <td className="px-3 py-2.5">
                        <div className="flex items-center gap-2">
                          <FileText className="h-4 w-4 text-muted-foreground" />
                          <span className="font-medium text-foreground">{d.filename}</span>
                        </div>
                      </td>
                      <td className="px-3 py-2.5">
                        <Badge variant="outline">{(d.format ?? "pdf").toUpperCase()}</Badge>
                      </td>
                      <td className="px-3 py-2.5 font-mono text-xs text-muted-foreground">
                        {d.doc_id.slice(0, 8)}…
                      </td>
                      <td className="px-3 py-2.5">
                        <Link
                          href={`/library/${d.doc_id}`}
                          className="text-sm text-primary hover:underline"
                        >
                          Open →
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
