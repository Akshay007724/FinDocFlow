"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusPill } from "@/components/status-pill";
import { useHealth } from "@/lib/hooks/use-health";

export default function PipelinePage() {
  const { data, loading } = useHealth(5_000);
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight text-foreground">Pipeline Monitor</h2>
        <p className="text-sm text-muted-foreground">
          Live health of ingestion → extraction → linking → reasoning.
        </p>
      </div>
      <section className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
        {loading && !data
          ? Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="shimmer h-32 rounded-lg" />
            ))
          : (data ?? []).map((s) => (
              <Card key={s.service}>
                <CardHeader>
                  <CardTitle className="text-sm capitalize">{s.service}</CardTitle>
                </CardHeader>
                <CardContent className="flex flex-col gap-2">
                  <StatusPill status={s.error ? "failed" : "done"} label={s.error ? "down" : "ok"} />
                  <div className="font-mono text-[0.65rem] text-muted-foreground break-all">{s.url}</div>
                  {s.health?.model && (
                    <div className="font-mono text-[0.7rem] text-foreground/80">model: {s.health.model}</div>
                  )}
                  {s.error && (
                    <div className="text-[0.7rem] text-destructive">{s.error}</div>
                  )}
                </CardContent>
              </Card>
            ))}
      </section>
    </div>
  );
}
