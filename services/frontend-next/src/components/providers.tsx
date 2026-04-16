"use client";

import * as React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";
import { CommandPaletteProvider } from "@/components/shell/command-palette-context";
import { ShortcutsBridge } from "@/components/shell/shortcuts-bridge";

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = React.useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 15_000,
            refetchOnWindowFocus: false,
            retry: 1,
          },
        },
      })
  );

  return (
    <QueryClientProvider client={client}>
      <CommandPaletteProvider>
        <ShortcutsBridge />
        {children}
        <Toaster
          theme="dark"
          richColors
          closeButton
          toastOptions={{
            style: {
              background: "hsl(var(--card))",
              color: "hsl(var(--card-foreground))",
              border: "1px solid hsl(var(--border))",
            },
          }}
        />
      </CommandPaletteProvider>
    </QueryClientProvider>
  );
}
