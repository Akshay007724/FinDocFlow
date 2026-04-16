"use client";

import { useEffect, useRef, useState } from "react";
import type { JobStatus } from "@/lib/api/types";

export function useIngestWebSocket(jobId: string | null) {
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!jobId) return;
    setStatus(null);
    setError(null);
    setConnected(false);

    const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
    const base = process.env.NEXT_PUBLIC_INGESTION_URL;
    let url: string;
    if (base) {
      // Direct, bypassing the Next.js proxy (WS upgrade doesn't pass through rewrites reliably)
      url = base.replace(/^http/, "ws") + `/ingest/ws/${jobId}`;
    } else {
      url = `${scheme}//${window.location.host}/api/ingestion/ingest/ws/${jobId}`;
    }

    let ws: WebSocket;
    try {
      ws = new WebSocket(url);
      ref.current = ws;
    } catch (err) {
      setError((err as Error).message);
      return;
    }

    ws.onopen = () => setConnected(true);
    ws.onmessage = (ev) => {
      try {
        const parsed = JSON.parse(ev.data) as JobStatus;
        setStatus(parsed);
        if (parsed.status === "done" || parsed.status === "failed") {
          ws.close();
        }
      } catch (err) {
        setError((err as Error).message);
      }
    };
    ws.onerror = () => {
      setError("WebSocket connection failed");
      setConnected(false);
    };
    ws.onclose = () => {
      setConnected(false);
    };

    return () => {
      ws.close();
    };
  }, [jobId]);

  return { status, connected, error };
}
