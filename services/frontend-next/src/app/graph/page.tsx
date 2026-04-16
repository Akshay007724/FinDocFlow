"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/empty-state";
import { Network } from "lucide-react";

export default function GraphPage() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight text-foreground">Knowledge Graph</h2>
        <p className="text-sm text-muted-foreground">
          Cross-page entities resolved in Neo4j — companies, metrics, periods.
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Force-directed view</CardTitle>
        </CardHeader>
        <CardContent>
          <EmptyState
            icon={Network}
            title="Graph view preview"
            description="Ingest documents and enable entity-linking to populate the Neo4j graph. An interactive force-directed view is shipped in a follow-up. For now, query the graph via POST /graph/company-metrics on :8003."
          />
        </CardContent>
      </Card>
    </div>
  );
}
