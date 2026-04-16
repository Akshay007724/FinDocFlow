"use client";

import { Search, Bell, CircleDot, AlertCircle, Activity } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { useHealth } from "@/lib/hooks/use-health";
import { usePathname } from "next/navigation";
import { useCommandPalette } from "./command-palette-context";

const titles: Record<string, string> = {
  "/": "Dashboard",
  "/library": "Document Library",
  "/reports": "Report Generator",
  "/chat": "Chat",
  "/graph": "Knowledge Graph",
  "/pipeline": "Pipeline Monitor",
};

export function Topbar() {
  const pathname = usePathname();
  const { summary, data, loading } = useHealth();
  const { open: openPalette } = useCommandPalette();

  const title = titles[pathname] ?? "FinDocFlow";
  const allUp = !loading && summary.up === summary.total && summary.total > 0;

  return (
    <TooltipProvider delayDuration={200}>
      <header className="flex h-14 shrink-0 items-center justify-between gap-4 border-b border-border/60 bg-background/80 px-4 backdrop-blur-sm md:px-6">
        <div className="flex items-center gap-3">
          <h1 className="text-sm font-semibold text-foreground md:text-base">{title}</h1>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            className="hidden md:inline-flex gap-2 text-muted-foreground"
            onClick={openPalette}
            aria-label="Open command palette (Cmd+K)"
          >
            <Search className="h-3.5 w-3.5" aria-hidden="true" />
            <span>Search</span>
            <kbd className="ml-2 rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[0.65rem]">
              ⌘K
            </kbd>
          </Button>

          <Tooltip>
            <TooltipTrigger asChild>
              <button
                aria-label={allUp ? "All services healthy" : "Service health warning"}
                className="inline-flex h-9 w-9 items-center justify-center rounded-md hover:bg-muted"
              >
                {loading ? (
                  <Activity className="h-4 w-4 text-muted-foreground" />
                ) : allUp ? (
                  <CircleDot className="h-4 w-4 text-accent" />
                ) : (
                  <AlertCircle className="h-4 w-4 text-warning" />
                )}
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom">
              <div className="space-y-1 py-1">
                <div className="font-medium">Service health</div>
                {data?.map((s) => (
                  <div key={s.service} className="flex items-center justify-between gap-4 font-mono text-[0.65rem]">
                    <span className="text-muted-foreground">{s.service}</span>
                    <span className={s.error ? "text-destructive" : "text-accent"}>
                      {s.error ? "down" : "ok"}
                    </span>
                  </div>
                ))}
                {!data && <div className="text-muted-foreground">Checking…</div>}
              </div>
            </TooltipContent>
          </Tooltip>

          <Button variant="ghost" size="icon" aria-label="Notifications">
            <Bell className="h-4 w-4" />
          </Button>
        </div>
      </header>
    </TooltipProvider>
  );
}
