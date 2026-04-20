"use client";

import { useShortcuts } from "@/lib/hooks/use-shortcuts";

export function ShortcutsBridge() {
  useShortcuts();
  return null;
}
