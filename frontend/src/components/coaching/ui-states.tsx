"use client";

import { cn } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-surface-muted", className)} aria-hidden />;
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-border bg-surface px-3 py-4 text-center" role="status">
      <h2 className="text-sm font-semibold text-foreground">{title}</h2>
      {description ? <p className="mt-1 text-xs text-muted-foreground">{description}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

export function ErrorState({
  title = "Noe gikk galt",
  description,
  onRetry,
}: {
  title?: string;
  description?: string;
  onRetry?: () => void;
}) {
  return (
    <div
      className="rounded-xl border border-status-critical/30 bg-status-critical/5 px-3 py-3"
      role="alert"
    >
      <h2 className="text-sm font-semibold text-status-critical">{title}</h2>
      {description ? <p className="mt-1 text-xs text-muted-foreground">{description}</p> : null}
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-2 rounded-md bg-foreground px-2.5 py-1.5 text-xs text-background"
        >
          Prøv igjen
        </button>
      ) : null}
    </div>
  );
}

export function StaleDataState({ message }: { message: string }) {
  return (
    <div
      className="rounded-md border border-status-warning/40 bg-status-warning/10 px-2.5 py-1.5 text-xs text-foreground"
      role="status"
    >
      <span className="font-medium">Utdatert data · </span>
      {message}
    </div>
  );
}

export function StatusBadge({
  status,
  label,
}: {
  status: "positive" | "neutral" | "warning" | "critical" | "info" | "muted";
  label: string;
}) {
  const styles: Record<string, string> = {
    positive: "bg-status-positive/15 text-status-positive",
    neutral: "bg-status-neutral/15 text-status-neutral",
    warning: "bg-status-warning/15 text-status-warning",
    critical: "bg-status-critical/15 text-status-critical",
    info: "bg-status-info/15 text-status-info",
    muted: "bg-muted text-muted-foreground",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium",
        styles[status]
      )}
    >
      {label}
    </span>
  );
}
