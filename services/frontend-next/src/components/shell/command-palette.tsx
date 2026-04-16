"use client";

import * as React from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Command } from "cmdk";
import { useRouter } from "next/navigation";
import {
  LayoutDashboard,
  Library,
  FileText,
  MessageSquare,
  Network,
  Activity,
  Upload,
  Sparkles,
} from "lucide-react";
import { useCommandPalette } from "./command-palette-context";
import { cn } from "@/lib/utils";

type PaletteItem = {
  group: "Navigation" | "Actions";
  label: string;
  path: string;
  icon: React.ComponentType<{ className?: string }>;
  hint?: string;
};

const navTargets: PaletteItem[] = [
  { group: "Navigation", label: "Dashboard", path: "/", icon: LayoutDashboard, hint: "g d" },
  { group: "Navigation", label: "Library", path: "/library", icon: Library, hint: "g l" },
  { group: "Navigation", label: "Reports", path: "/reports", icon: FileText, hint: "g r" },
  { group: "Navigation", label: "Chat", path: "/chat", icon: MessageSquare, hint: "g c" },
  { group: "Navigation", label: "Knowledge Graph", path: "/graph", icon: Network, hint: "g g" },
  { group: "Navigation", label: "Pipeline Monitor", path: "/pipeline", icon: Activity, hint: "g p" },
];

const actions: PaletteItem[] = [
  { group: "Actions", label: "Upload a document", path: "/library?upload=1", icon: Upload },
  { group: "Actions", label: "Generate a new report", path: "/reports", icon: Sparkles },
  { group: "Actions", label: "Start a chat", path: "/chat", icon: MessageSquare },
];

export function CommandPalette() {
  const router = useRouter();
  const { isOpen, close } = useCommandPalette();

  const items = [...navTargets, ...actions];

  const go = (path: string) => {
    close();
    router.push(path);
  };

  return (
    <DialogPrimitive.Root open={isOpen} onOpenChange={(o) => !o && close()}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-background/70 backdrop-blur-sm data-[state=open]:animate-in data-[state=open]:fade-in-0" />
        <DialogPrimitive.Content
          className="fixed left-1/2 top-[18%] z-50 w-[90vw] max-w-xl -translate-x-1/2 rounded-lg border border-border bg-card p-0 shadow-xl focus-visible:outline-none"
          aria-label="Command palette"
        >
          <DialogPrimitive.Title className="sr-only">Command palette</DialogPrimitive.Title>
          <Command
            label="Command palette"
            className={cn("flex flex-col")}
          >
            <div className="border-b border-border/80 px-3">
              <Command.Input
                autoFocus
                placeholder="Search commands, documents, actions…"
                className="h-12 w-full bg-transparent text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
              />
            </div>
            <Command.List className="max-h-[320px] overflow-auto p-2">
              <Command.Empty className="p-4 text-sm text-muted-foreground">
                No results. Press Esc to close.
              </Command.Empty>
              {["Navigation", "Actions"].map((group) => (
                <Command.Group key={group} heading={group} className="px-1 pb-2 text-[0.65rem] font-semibold uppercase tracking-widest text-muted-foreground">
                  {items
                    .filter((i) => i.group === group)
                    .map(({ label, path, icon: Icon, hint }) => (
                      <Command.Item
                        key={label}
                        value={`${group} ${label}`}
                        onSelect={() => go(path)}
                        className={cn(
                          "flex items-center gap-3 rounded-md px-3 py-2 text-sm text-foreground cursor-pointer",
                          "aria-selected:bg-primary/10 aria-selected:text-primary"
                        )}
                      >
                        <Icon className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                        <span className="flex-1">{label}</span>
                        {hint ? (
                          <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[0.65rem] text-muted-foreground">
                            {hint}
                          </kbd>
                        ) : null}
                      </Command.Item>
                    ))}
                </Command.Group>
              ))}
            </Command.List>
          </Command>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
