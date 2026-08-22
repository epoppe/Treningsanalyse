"use client";

import { cn } from "@/lib/utils";
import type { EvidenceBand } from "@/types/analysis";

export function EvidenceBadge({ evidence }: { evidence: EvidenceBand | string }) {
  const e = (evidence || "insufficient").toLowerCase();
  const styles: Record<string, string> = {
    strong: "bg-emerald-100 text-emerald-800",
    supported: "bg-sky-100 text-sky-800",
    emerging: "bg-amber-100 text-amber-900",
    insufficient: "bg-slate-100 text-slate-600",
    moderate: "bg-sky-100 text-sky-800",
    weak: "bg-amber-100 text-amber-900",
  };
  const labels: Record<string, string> = {
    strong: "Sterk evidens",
    supported: "Støttet",
    emerging: "Fremvoksende",
    insufficient: "Utilstrekkelig",
    moderate: "Moderat",
    weak: "Svak",
  };
  return (
    <span className={cn("inline-flex rounded px-1.5 py-0.5 text-[10px] font-medium", styles[e] || styles.insufficient)}>
      {labels[e] || evidence}
    </span>
  );
}

export function AnalysisEmpty({ title, description }: { title: string; description?: string }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-white px-3 py-6 text-center" role="status">
      <p className="text-sm font-medium text-slate-800">{title}</p>
      {description ? <p className="mt-1 text-xs text-slate-500">{description}</p> : null}
    </div>
  );
}

export function AnalysisError({
  title,
  description,
  onRetry,
}: {
  title: string;
  description?: string;
  onRetry?: () => void;
}) {
  const safeDescription = (() => {
    if (!description) return undefined;
    const trimmed = description.trim();
    if (trimmed.length <= 220) return trimmed;
    // Avoid dumping raw SQL/traceback blobs into the UI.
    if (trimmed.includes("sqlite3") || trimmed.includes("Traceback") || trimmed.includes("SELECT ")) {
      return "Midlertidig databasefeil under parallell lasting. Prøv igjen.";
    }
    return `${trimmed.slice(0, 200)}…`;
  })();

  return (
    <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-3" role="alert">
      <p className="text-sm font-medium text-red-800">{title}</p>
      {safeDescription ? <p className="mt-1 text-xs text-red-700/80">{safeDescription}</p> : null}
      {onRetry ? (
        <button type="button" onClick={onRetry} className="mt-2 text-xs font-medium text-red-700 underline">
          Prøv igjen
        </button>
      ) : null}
    </div>
  );
}

export function AnalysisSkeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-slate-100", className)} aria-hidden />;
}
