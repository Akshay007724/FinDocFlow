import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowUpRight, ArrowDownRight, type LucideIcon } from "lucide-react";
import { cn, formatDelta } from "@/lib/utils";

interface KpiTileProps {
  label: string;
  value?: string;
  delta?: number;
  deltaLabel?: string;
  icon?: LucideIcon;
  loading?: boolean;
  hint?: string;
}

export function KpiTile({ label, value, delta, deltaLabel, icon: Icon, loading, hint }: KpiTileProps) {
  const deltaUp = (delta ?? 0) >= 0;
  return (
    <Card className="relative overflow-hidden">
      <CardContent className="p-5">
        <div className="flex items-start justify-between">
          <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            {label}
          </span>
          {Icon && <Icon className="h-4 w-4 text-muted-foreground" aria-hidden="true" />}
        </div>
        {loading ? (
          <Skeleton className="mt-3 h-9 w-24" />
        ) : (
          <div className="mt-2 font-mono text-3xl font-medium leading-none text-foreground">
            {value ?? "—"}
          </div>
        )}
        {typeof delta === "number" && !loading && (
          <div
            className={cn(
              "mt-2 inline-flex items-center gap-1 text-xs",
              deltaUp ? "text-accent" : "text-destructive"
            )}
          >
            {deltaUp ? (
              <ArrowUpRight className="h-3 w-3" aria-hidden="true" />
            ) : (
              <ArrowDownRight className="h-3 w-3" aria-hidden="true" />
            )}
            <span>{formatDelta(delta)}</span>
            {deltaLabel && <span className="text-muted-foreground">{deltaLabel}</span>}
          </div>
        )}
        {hint && !loading && (
          <div className="mt-1 text-xs text-muted-foreground">{hint}</div>
        )}
      </CardContent>
    </Card>
  );
}
