"use client";

import { useCallback, useRef, useState } from "react";
import { Upload, FileUp, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { uploadDocument } from "@/lib/api/ingestion";
import { toast } from "sonner";
import { useIngestWebSocket } from "@/lib/hooks/use-ingest-ws";
import type { JobStatus } from "@/lib/api/types";

interface UploadZoneProps {
  onIngested?: (docIds: string[]) => void;
}

interface ActiveJob {
  jobId: string;
  filename: string;
  docIds: string[];
  initialStatus: JobStatus;
}

export function UploadZone({ onIngested }: UploadZoneProps) {
  const [dragActive, setDragActive] = useState(false);
  const [jobs, setJobs] = useState<ActiveJob[]>([]);
  const fileInput = useRef<HTMLInputElement>(null);

  const handleFiles = useCallback(
    async (files: FileList | File[]) => {
      const list = Array.from(files);
      for (const file of list) {
        try {
          const status = await uploadDocument(file);
          setJobs((prev) => [
            ...prev,
            { jobId: status.job_id, filename: file.name, docIds: status.doc_ids, initialStatus: status },
          ]);
          toast.success(`Queued ${file.name}`);
        } catch (err) {
          toast.error(`Failed to upload ${file.name}`, {
            description: (err as Error).message,
          });
        }
      }
    },
    []
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragActive(false);
      if (e.dataTransfer.files?.length) void handleFiles(e.dataTransfer.files);
    },
    [handleFiles]
  );

  return (
    <div className="flex flex-col gap-3">
      <label
        htmlFor="upload-input"
        onDragOver={(e) => {
          e.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={onDrop}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed px-6 py-10 text-center transition-colors",
          dragActive
            ? "border-primary/70 bg-primary/10"
            : "border-border hover:border-border/80 hover:bg-muted/40"
        )}
      >
        <div className="rounded-full bg-muted p-3">
          <FileUp className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
        </div>
        <div className="text-sm font-medium text-foreground">Drop files here or click to browse</div>
        <div className="text-xs text-muted-foreground">PDF · HTML · XBRL · Excel · multi-file supported</div>
        <input
          id="upload-input"
          ref={fileInput}
          type="file"
          accept=".pdf,.html,.htm,.xbrl,.xml,.xlsx,.xls"
          multiple
          className="sr-only"
          onChange={(e) => e.target.files && handleFiles(e.target.files)}
        />
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="mt-2"
          onClick={() => fileInput.current?.click()}
        >
          <Upload className="h-3.5 w-3.5" aria-hidden="true" />
          Browse files
        </Button>
      </label>

      {jobs.length > 0 && (
        <div className="flex flex-col gap-2">
          {jobs.map((job) => (
            <JobProgress
              key={job.jobId}
              job={job}
              onDismiss={() =>
                setJobs((prev) => prev.filter((j) => j.jobId !== job.jobId))
              }
              onDone={(ids) => onIngested?.(ids)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function JobProgress({
  job,
  onDismiss,
  onDone,
}: {
  job: ActiveJob;
  onDismiss: () => void;
  onDone: (docIds: string[]) => void;
}) {
  const { status, error } = useIngestWebSocket(job.jobId);
  const current = status ?? job.initialStatus;
  const pct = Math.max(1, current.progress);
  const isDone = current.status === "done";
  const isFailed = current.status === "failed" || !!error;

  if (isDone) {
    // Fire once
    setTimeout(() => onDone(job.docIds), 0);
  }

  return (
    <div className="flex items-center gap-3 rounded-md border border-border bg-card px-3 py-2">
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-3">
          <div className="truncate text-sm text-foreground">{job.filename}</div>
          <div className="font-mono text-xs text-muted-foreground">{pct}%</div>
        </div>
        <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-muted">
          <div
            className={cn(
              "h-full rounded-full transition-[width] duration-300",
              isFailed ? "bg-destructive" : isDone ? "bg-accent" : "bg-primary"
            )}
            style={{ width: `${pct}%` }}
          />
        </div>
        {current.message && (
          <div className="mt-1 text-xs text-muted-foreground">{current.message}</div>
        )}
        {error && <div className="mt-1 text-xs text-destructive">{error}</div>}
      </div>
      <button
        onClick={onDismiss}
        className="text-muted-foreground hover:text-foreground"
        aria-label={`Dismiss ${job.filename}`}
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}
