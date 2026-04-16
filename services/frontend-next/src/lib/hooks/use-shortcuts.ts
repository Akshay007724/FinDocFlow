"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

const vimNav: Record<string, string> = {
  d: "/",
  l: "/library",
  r: "/reports",
  c: "/chat",
  g: "/graph",
  p: "/pipeline",
};

export function useShortcuts() {
  const router = useRouter();
  useEffect(() => {
    let leader: string | null = null;
    let leaderTimer: ReturnType<typeof setTimeout> | null = null;

    const clearLeader = () => {
      leader = null;
      if (leaderTimer) clearTimeout(leaderTimer);
    };

    const handler = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t?.tagName === "INPUT" || t?.tagName === "TEXTAREA" || t?.isContentEditable) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      if (leader === "g") {
        const target = vimNav[e.key.toLowerCase()];
        if (target) {
          e.preventDefault();
          router.push(target);
        }
        clearLeader();
        return;
      }
      if (e.key === "g") {
        leader = "g";
        if (leaderTimer) clearTimeout(leaderTimer);
        leaderTimer = setTimeout(clearLeader, 900);
      }
    };
    window.addEventListener("keydown", handler);
    return () => {
      window.removeEventListener("keydown", handler);
      if (leaderTimer) clearTimeout(leaderTimer);
    };
  }, [router]);
}
