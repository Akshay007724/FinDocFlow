"use client";

import { useEffect, useState } from "react";
import { checkAll, type ServiceHealth } from "@/lib/api/health";

export function useHealth(intervalMs = 15_000) {
  const [data, setData] = useState<ServiceHealth[] | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function tick() {
      try {
        const next = await checkAll();
        if (!cancelled) setData(next);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    tick();
    const t = setInterval(tick, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [intervalMs]);

  const summary = data
    ? {
        total: data.length,
        up: data.filter((s) => !s.error && s.health?.status === "ok").length,
      }
    : { total: 0, up: 0 };

  return { data, loading, summary };
}
