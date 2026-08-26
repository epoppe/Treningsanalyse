"use client";

import { useState } from "react";
import Link from "next/link";
import { WeeklyPlanStrip } from "@/components/cockpit/WeeklyPlanStrip";
import { PlanHorizonNav, type PlanHorizon } from "@/components/cockpit/PlanHorizonNav";
import { PlanChangeTimeline } from "@/components/cockpit/PlanChangeTimeline";
import { PlanVsActualTable } from "@/components/cockpit/PlanVsActualTable";
import { MesocycleOverview } from "@/components/cockpit/MesocycleOverview";
import { NextWorkoutCard } from "@/components/cockpit/NextWorkoutCard";
import { AnalysisError, AnalysisSkeleton } from "@/components/analysis/ui";
import { RecommendationHistoryPanel } from "@/components/cockpit/RecommendationHistoryPanel";
import { phaseLabel, planReasonLabel, workoutTypeLabel } from "@/components/cockpit/cockpitUtils";
import { usePlan } from "@/hooks/usePlan";
import { useTodayDashboard } from "@/hooks/useTodayDashboard";
import type { TodayDashboardPayload } from "@/types/today";

function todaySession(data: ReturnType<typeof usePlan>["data"]) {
  if (!data?.weekly_plan?.sessions?.length) return null;
  const todayOffset = data.as_of
    ? (() => {
        const day = new Date(`${data.as_of}T12:00:00`).getDay();
        return day === 0 ? 6 : day - 1;
      })()
    : new Date().getDay() === 0
      ? 6
      : new Date().getDay() - 1;
  return data.weekly_plan.sessions.find((s) => (s.day_offset ?? -1) === todayOffset) || null;
}

function toTodayPayload(data: ReturnType<typeof usePlan>["data"]): TodayDashboardPayload | null {
  if (!data) return null;
  const session = todaySession(data);
  return {
    as_of: data.as_of,
    recommendation: session
      ? {
          decision_status: "recommend",
          workout_type: session.type,
          workout: {
            type: session.type,
            duration_min: Array.isArray(session.duration_min)
              ? session.duration_min[0]
              : session.duration_min,
          },
        }
      : undefined,
  };
}

export default function PlanPage() {
  const [horizon, setHorizon] = useState<PlanHorizon>("week");
  const query = usePlan();
  const data = query.data;
  const hasPlanSession = Boolean(data?.weekly_plan?.sessions?.length);
  const todayQuery = useTodayDashboard(undefined, !query.isLoading && !hasPlanSession);

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
  const todayPayload = toTodayPayload(data) || todayQuery.data;
  const completionRate = data.vs_actual?.summary?.completion_rate;

  return (
    <div className="space-y-4">
      <header className="space-y-3">
        <div className="space-y-1">
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
            Plan
          </p>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Treningsplan</h1>
          {data.goal?.target_event ? (
            <p className="text-sm text-slate-600">Mål: {String(data.goal.target_event)}</p>
          ) : null}
          {data.training_phase?.phase ? (
            <p className="text-sm text-slate-600">
              Fase: {phaseLabel(String(data.training_phase.phase))}
            </p>
          ) : null}
        </div>
        <PlanHorizonNav value={horizon} onChange={setHorizon} />
      </header>

      {horizon === "today" && todayPayload ? (
        <NextWorkoutCard data={todayPayload} />
      ) : null}

      {horizon === "week" ? (
        <>
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
                        {session.duration_min
                          ? ` · ${
                              Array.isArray(session.duration_min)
                                ? `${session.duration_min[0]}–${session.duration_min[1]}`
                                : session.duration_min
                            } min`
                          : ""}
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

          {data.plan_adaptation?.reason?.length ? (
            <section className="rounded-xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
              <h2 className="text-sm font-semibold text-slate-900">Planjustering</h2>
              <ul className="mt-2 list-inside list-disc text-sm text-slate-600">
                {(data.plan_adaptation.reason || []).map((reason) => (
                  <li key={reason}>{planReasonLabel(String(reason))}</li>
                ))}
              </ul>
            </section>
          ) : null}

          <section className="rounded-xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-sm font-semibold text-slate-900">Plan vs. faktisk</h2>
              {completionRate != null ? (
                <span className="text-xs text-slate-500 tabular-nums">
                  {Math.round(completionRate * 100)}% gjennomført
                </span>
              ) : null}
            </div>
            <PlanVsActualTable days={data.vs_actual?.days} />
          </section>

          <section className="rounded-xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
            <h2 className="text-sm font-semibold text-slate-900">Planendringer</h2>
            <p className="mt-1 text-xs text-slate-500">
              Historikk over justeringer — uten tekniske versjonsdetaljer.
            </p>
            <PlanChangeTimeline history={data.version_history} />
          </section>
        </>
      ) : null}

      {horizon === "mesocycle" ? (
        <section className="rounded-xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
          <h2 className="text-sm font-semibold text-slate-900">Mesosyklus</h2>
          {data.mesocycle?.note ? (
            <p className="mt-1 text-xs text-slate-500">{data.mesocycle.note}</p>
          ) : null}
          <MesocycleOverview weeks={data.mesocycle?.mesocycle} />
        </section>
      ) : null}

      <RecommendationHistoryPanel />

      <Link href="/" className="inline-block text-sm font-medium text-slate-900 underline">
        Tilbake til I dag
      </Link>
    </div>
  );
}
