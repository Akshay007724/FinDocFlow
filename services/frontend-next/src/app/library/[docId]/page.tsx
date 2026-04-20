"use client";

import { useQuery } from "@tanstack/react-query";
import { getPages } from "@/lib/api/ingestion";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/empty-state";
import { FileText, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { useParams } from "next/navigation";

export default function DocumentDetailPage() {
  const { docId } = useParams<{ docId: string }>();
  const pagesQ = useQuery({
    queryKey: ["doc", docId],
    queryFn: () => getPages(docId),
    enabled: !!docId,
  });

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="font-mono text-xs text-muted-foreground">doc_id: {docId}</h2>
          <p className="text-xl font-semibold tracking-tight text-foreground">
            Document inspector
          </p>
        </div>
        <div className="flex gap-2">
          <Button asChild variant="outline">
            <Link href={`/chat?doc=${docId}`}>Ask a question</Link>
          </Button>
          <Button asChild>
            <Link href={`/reports?doc=${docId}`}>
              <Sparkles className="h-4 w-4" /> Generate report
            </Link>
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">Pages</CardTitle>
          {pagesQ.data && (
            <Badge variant="outline">{pagesQ.data.length} pages cached</Badge>
          )}
        </CardHeader>
        <CardContent>
          {pagesQ.isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="shimmer h-16 rounded-md" />
              ))}
            </div>
          ) : pagesQ.isError ? (
            <EmptyState
              icon={FileText}
              title="Pages unavailable"
              description="This document's cache may have expired. Re-upload to continue."
            />
          ) : !pagesQ.data?.length ? (
            <EmptyState
              icon={FileText}
              title="No pages extracted"
              description="Extraction may still be in-flight. Check the pipeline monitor."
            />
          ) : (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {pagesQ.data.map((page) => (
                <div
                  key={page.page_num}
                  className="rounded-md border border-border/60 bg-muted/30 p-3"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs text-muted-foreground">
                      Page {page.page_num}
                    </span>
                    <div className="flex gap-1.5">
                      {page.has_tables && <Badge variant="outline">tables</Badge>}
                      {page.has_images && <Badge variant="outline">images</Badge>}
                    </div>
                  </div>
                  <p className="mt-2 line-clamp-4 text-xs text-foreground/80">
                    {page.text || <span className="italic text-muted-foreground">No text extracted</span>}
                  </p>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
