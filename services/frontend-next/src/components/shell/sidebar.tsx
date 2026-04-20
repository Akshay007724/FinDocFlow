"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Library, FileText, MessageSquare, Network, Activity } from "lucide-react";
import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

const items = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard, key: "d" },
  { href: "/library", label: "Library", icon: Library, key: "l" },
  { href: "/reports", label: "Reports", icon: FileText, key: "r" },
  { href: "/chat", label: "Chat", icon: MessageSquare, key: "c" },
  { href: "/graph", label: "Knowledge Graph", icon: Network, key: "g" },
  { href: "/pipeline", label: "Pipeline", icon: Activity, key: "p" },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <TooltipProvider delayDuration={200}>
      <aside className="hidden md:flex md:w-[220px] lg:w-[240px] shrink-0 flex-col border-r border-border/60 bg-card/40">
        <div className="flex h-14 items-center gap-2 px-5 border-b border-border/50">
          <div className="h-6 w-6 rounded-md bg-gradient-to-br from-primary to-accent" aria-hidden="true" />
          <span className="font-semibold tracking-tight text-foreground">FinDocFlow</span>
        </div>
        <nav className="flex-1 overflow-y-auto px-2 py-3" aria-label="Primary">
          <ul className="flex flex-col gap-0.5">
            {items.map(({ href, label, icon: Icon, key }) => {
              const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
              return (
                <li key={href}>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Link
                        href={href}
                        className={cn(
                          "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors duration-150",
                          active
                            ? "bg-primary/10 text-primary nav-glow"
                            : "text-muted-foreground hover:bg-muted hover:text-foreground"
                        )}
                        aria-current={active ? "page" : undefined}
                      >
                        <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                        <span>{label}</span>
                      </Link>
                    </TooltipTrigger>
                    <TooltipContent side="right">
                      Shortcut: <kbd className="font-mono text-[0.7rem]">g {key}</kbd>
                    </TooltipContent>
                  </Tooltip>
                </li>
              );
            })}
          </ul>
        </nav>
        <div className="border-t border-border/50 px-4 py-3 text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <span className="live-dot" />
            <span>Live</span>
          </div>
          <div className="mt-1 font-mono text-[0.65rem]">v0.1.0 · feat/frontend-next</div>
        </div>
      </aside>
    </TooltipProvider>
  );
}
