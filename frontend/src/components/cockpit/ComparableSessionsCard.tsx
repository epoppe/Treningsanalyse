"use client";

import Link from "next/link";
import type { ComparableSessionsPayload } from "@/types/dashboard";
import { AnalysisError, AnalysisSkeleton } from "@/components/analysis/ui";
import { useComparableSessions } from "@/hooks/useDashboard";
import { workoutTypeLabel } from "./cockpitUtils";

export function ComparableSessionsCard({
  data,
  isLoading,
  isError,
  onRetry,
}: {
  data?: ComparableSessionsPayload;
  isLoading?: boolean;
  isError?: boolean;
  onRetry?: () => void;
}) {
  if (isLoading) return <AnalysisSkeleton className="h-28" />;
  if (isError) {
    return (
      <AnalysisError title="Kunne ikke hente sammenlignbare økter" onRetry={onRetry} />
    );
  }
  if (!data || data.status !== "ok") return null;

  const percentile = data.percentile_vs_comparable;
  const quality = data.current_quality as { quality_score?: number; session_type?: string } | undefined;

  return (
    <section className="rounded-xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
      <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
        Sammenlignbar økt
      </p>
      <h2 className="mt-1 text-lg font-semibold text-slate-900">Vs. dine lignende økter</h2>
      <p className="mt-1 text-sm text-slate-600">
        {workoutTypeLabel(quality?.session_type)} · kvalitet{" "}
        {quality?.quality_score != null ? quality.quality_score : "—"}
        {data.comparable_count ? ` · ${data.comparable_count} sammenlignbare` : ""}
      </p>
      {percentile != null ? (
        <p className="mt-2 text-sm text-slate-700">
          Percentil vs. sammenlignbare: {percentile}% (høyere er bedre)
        </p>
      ) : (
        <p className="mt-2 text-sm text-slate-600">For få sammenlignbare økter til percentil.</p>
      )}
      {data.limitations?.length ? (
        <p className="mt-1 text-xs text-amber-700">{data.limitations.join(" · ")}</p>
      ) : null}
      {data.matches?.length ? (
        <ul className="mt-3 space-y-1 text-xs text-slate-600">
          {data.matches.slice(0, 3).map((match) => (
            <li key={match.activity_id} className="flex justify-between gap-2">
              <span>{match.activity_name || match.date}</span>
              {match.activity_id ? (
                <Link href={`/activities/${match.activity_id}`} className="underline">
                  Se
                </Link>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

export function ComparableSessionsSection({ activityId }: { activityId: string }) {
  const query = useComparableSessions(activityId);

  return (
    <ComparableSessionsCard
      data={query.data}
      isLoading={query.isLoading}
      isError={query.isError}
      onRetry={() => query.refetch()}
    />
  );
}
