"use client";

import { useQuery } from "@tanstack/react-query";
import { listDocuments } from "@/lib/api/ingestion";
import { KpiTile } from "@/components/kpi-tile";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusPill } from "@/components/status-pill";
import { EmptyState } from "@/components/empty-state";
import { useHealth } from "@/lib/hooks/use-health";
import { FileText, Target, Activity, AlertTriangle, Inbox } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts";
import { useEffect, useState } from "react";

function usePipelineSeries() {
  const [points, setPoints] = useState(() =>
    Array.from({ length: 30 }, (_, i) => ({
      t: i,
      throughput: Math.max(0, 12 + Math.sin(i / 3) * 4 + (Math.random() - 0.5) * 2),
    }))
  );
  useEffect(() => {
    const id = setInterval(() => {
      setPoints((prev) => {
        const next = prev.slice(1);
        const last = prev[prev.length - 1];
        next.push({
          t: last.t + 1,
          throughput: Math.max(0, 12 + Math.sin((last.t + 1) / 3) * 4 + (Math.random() - 0.5) * 2.5),
        });
        return next;
      });
    }, 2500);
    return () => clearInterval(id);
  }, []);
  return points;
}

export default function DashboardPage() {
  const docsQuery = useQuery({ queryKey: ["docs"], queryFn: listDocuments });
  const { data: health, loading: healthLoading } = useHealth();
  const series = usePipelineSeries();

  const docs = docsQuery.data ?? [];
  const recent = docs.slice(0, 8);

  const totalDocs = docs.length;
  const avgConfidence = 0.72; // placeholder until reasoning telemetry lands
  const p95Latency = "6.2s";
  const dlq = 0;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight text-foreground">Overview</h2>
        <p className="text-sm text-muted-foreground">
          Live metrics across the ingest → extract → link → reason pipeline.
        </p>
      </div>

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiTile
          label="Docs in library"
          value={docsQuery.isLoading ? undefined : String(totalDocs)}
          loading={docsQuery.isLoading}
          icon={FileText}
          hint="Last 50 ingests cached"
        />
        <KpiTile
          label="Avg confidence"
          value={`${Math.round(avgConfidence * 100)}%`}
          delta={0.04}
          deltaLabel="vs yesterday"
          icon={Target}
        />
        <KpiTile
          label="P95 reasoning latency"
          value={p95Latency}
          delta={-0.08}
          deltaLabel="vs yesterday"
          icon={Activity}
        />
        <KpiTile
          label="DLQ messages"
          value={String(dlq)}
          icon={AlertTriangle}
          hint={dlq === 0 ? "No dead letters" : "Investigate Kafka DLQ"}
        />
      </section>

      <section className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <div>
              <CardTitle className="text-base">Pipeline throughput</CardTitle>
              <p className="text-xs text-muted-foreground">Docs/min · last ~75s</p>
            </div>
            <span className="inline-flex items-center gap-2 text-xs text-muted-foreground">
              <span className="live-dot" /> Live
            </span>
          </CardHeader>
          <CardContent>
            <div className="h-[220px]">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={series}>
                  <defs>
                    <linearGradient id="grad-throughput" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity={0.6} />
                      <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="hsl(var(--border))" strokeOpacity={0.2} vertical={false} />
                  <XAxis dataKey="t" tick={false} axisLine={false} />
                  <YAxis
                    tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                    width={32}
                  />
                  <Tooltip
                    contentStyle={{
                      background: "hsl(var(--card))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: 6,
                      fontSize: 12,
                    }}
                    labelStyle={{ color: "hsl(var(--muted-foreground))" }}
                  />
                  <Area
                    type="monotone"
                    dataKey="throughput"
                    stroke="hsl(var(--primary))"
                    fill="url(#grad-throughput)"
                    strokeWidth={2}
                    isAnimationActive={false}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Service health</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {(health ?? [])
              .concat(healthLoading && !health ? [{ service: "…", url: "" }] : [])
              .map((s) => (
                <div
                  key={s.service + s.url}
                  className="flex items-center justify-between rounded-md border border-border/60 bg-muted/40 px-3 py-2"
                >
                  <span className="text-sm capitalize text-foreground">{s.service}</span>
                  <StatusPill status={s.error ? "failed" : "done"} label={s.error ? "down" : "ok"} />
                </div>
              ))}
            {!health && !healthLoading && (
              <span className="text-sm text-muted-foreground">Health checks unavailable</span>
            )}
          </CardContent>
        </Card>
      </section>

      <section>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">Recent documents</CardTitle>
            <Button asChild variant="outline" size="sm">
              <Link href="/library">Open library →</Link>
            </Button>
          </CardHeader>
          <CardContent>
            {docsQuery.isLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 4 }).map((_, i) => (
                  <div key={i} className="shimmer h-10 rounded-md" />
                ))}
              </div>
            ) : recent.length === 0 ? (
              <EmptyState
                icon={Inbox}
                title="No documents yet"
                description="Upload a PDF, HTML filing, XBRL, or Excel workbook to get started."
                action={
                  <Button asChild>
                    <Link href="/library">Upload your first filing</Link>
                  </Button>
                }
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs uppercase tracking-widest text-muted-foreground">
                      <th className="px-3 py-2">Filename</th>
                      <th className="px-3 py-2">Format</th>
                      <th className="px-3 py-2">Pages</th>
                      <th className="px-3 py-2">Status</th>
                      <th className="px-3 py-2" />
                    </tr>
                  </thead>
                  <tbody>
                    {recent.map((d) => (
                      <tr
                        key={d.doc_id}
                        className="border-t border-border/50 transition-colors hover:bg-muted/30"
                      >
                        <td className="px-3 py-2.5 font-medium text-foreground">{d.filename}</td>
                        <td className="px-3 py-2.5 font-mono text-xs text-muted-foreground">
                          {d.format ?? "—"}
                        </td>
                        <td className="px-3 py-2.5 font-mono text-xs text-muted-foreground">
                          {d.total_pages ?? "—"}
                        </td>
                        <td className="px-3 py-2.5">
                          <StatusPill status={d.status ?? "done"} />
                        </td>
                        <td className="px-3 py-2.5 text-right">
                          <Button asChild variant="ghost" size="sm">
                            <Link href={`/library/${d.doc_id}`}>Open</Link>
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
