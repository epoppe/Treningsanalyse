"use client";

import Link from "next/link";
import { WeeklyPlanStrip } from "@/components/cockpit/WeeklyPlanStrip";
import { AnalysisError, AnalysisSkeleton } from "@/components/analysis/ui";
import { workoutTypeLabel, planReasonLabel } from "@/components/cockpit/cockpitUtils";
import { useTodayDashboard } from "@/hooks/useTodayDashboard";

export default function PlanPage() {
  const query = useTodayDashboard();
  const data = query.data;

  if (query.isLoading) {
    return (
      <div className="space-y-4">
        <AnalysisSkeleton className="h-8 w-40" />
        <AnalysisSkeleton className="h-48 w-full" />
      </div>
    );
  }

  if (query.isError || !data) {
    return (
      <AnalysisError
        title="Kunne ikke hente plan"
        description={query.error instanceof Error ? query.error.message : undefined}
        onRetry={() => query.refetch()}
      />
    );
  }

  const sessions = data.weekly_plan?.sessions || [];

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
          Plan
        </p>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Ukeplan</h1>
        {data.goal?.target_event ? (
          <p className="text-sm text-slate-600">Mål: {String(data.goal.target_event)}</p>
        ) : null}
        {data.training_phase?.phase ? (
          <p className="text-sm text-slate-600">Fase: {String(data.training_phase.phase)}</p>
        ) : null}
      </header>

      <WeeklyPlanStrip data={data} />

      <section className="rounded-xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-900">Planlagte økter</h2>
        <div className="mt-3 space-y-2">
          {sessions.length > 0 ? (
            sessions.map((session, index) => (
              <div
                key={`${session.day_offset}-${session.type}-${index}`}
                className="flex items-center justify-between rounded-lg border border-slate-100 px-3 py-2"
              >
                <div>
                  <p className="text-sm font-medium text-slate-900">
                    {workoutTypeLabel(session.type)}
                  </p>
                  <p className="text-xs text-slate-500">
                    Dag +{session.day_offset ?? index}
                    {session.duration_min ? ` · ${session.duration_min} min` : ""}
                  </p>
                </div>
                <span className="text-xs text-slate-500">{session.purpose || "Planlagt"}</span>
              </div>
            ))
          ) : (
            <p className="text-sm text-slate-600">Ingen planlagte økter returnert.</p>
          )}
        </div>
      </section>

      {data.plan_adaptation?.reason ? (
        <section className="rounded-xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
          <h2 className="text-sm font-semibold text-slate-900">Planjustering</h2>
          <p className="mt-1 text-sm text-slate-600">
            {planReasonLabel(String(data.plan_adaptation.reason))}
          </p>
        </section>
      ) : null}

      <Link href="/" className="inline-block text-sm font-medium text-slate-900 underline">
        Tilbake til I dag
      </Link>
    </div>
  );
}
