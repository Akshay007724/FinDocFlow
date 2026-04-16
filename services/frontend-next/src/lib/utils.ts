import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatNumber(value: number, opts?: Intl.NumberFormatOptions) {
  return new Intl.NumberFormat("en-US", opts).format(value);
}

export function formatPercent(value: number, digits = 1) {
  return formatNumber(value, {
    style: "percent",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function formatDelta(delta: number) {
  const sign = delta > 0 ? "+" : delta < 0 ? "" : "";
  return `${sign}${formatPercent(delta, 1)}`;
}

export function formatDuration(ms: number) {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60_000)}m ${Math.round((ms % 60_000) / 1000)}s`;
}

export function relativeTime(iso: string) {
  const then = new Date(iso).getTime();
  const diff = Date.now() - then;
  const seconds = Math.round(diff / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

export function classForStatus(status: string) {
  switch (status) {
    case "done":
    case "completed":
    case "ok":
      return "bg-accent/15 text-accent border-accent/30";
    case "processing":
    case "pending":
      return "bg-primary/15 text-primary border-primary/30";
    case "failed":
    case "error":
      return "bg-destructive/15 text-destructive border-destructive/30";
    default:
      return "bg-warning/15 text-warning border-warning/30";
  }
}
