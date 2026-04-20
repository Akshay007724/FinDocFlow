import { cn, classForStatus } from "@/lib/utils";
import { Check, AlertCircle, Loader2, CircleDashed } from "lucide-react";

interface StatusPillProps {
  status: string;
  label?: string;
  className?: string;
}

const icons: Record<string, React.ComponentType<{ className?: string }>> = {
  done: Check,
  completed: Check,
  processing: Loader2,
  pending: CircleDashed,
  failed: AlertCircle,
  error: AlertCircle,
};

export function StatusPill({ status, label, className }: StatusPillProps) {
  const Icon = icons[status] ?? CircleDashed;
  const spinning = status === "processing";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium capitalize",
        classForStatus(status),
        className
      )}
      role="status"
      aria-label={`Status: ${label ?? status}`}
    >
      <Icon className={cn("h-3 w-3", spinning && "animate-spin")} aria-hidden="true" />
      {label ?? status}
    </span>
  );
}
