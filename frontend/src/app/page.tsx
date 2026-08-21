"use client";

import { AthleteStateCard } from "@/components/coaching/AthleteStateCard";
import { FormTrendStrip } from "@/components/coaching/FormTrendStrip";
import { NextWorkoutCard } from "@/components/coaching/NextWorkoutCard";
import { WeeklyTrainingPlan } from "@/components/coaching/WeeklyTrainingPlan";
import { WhyThisWorkout } from "@/components/coaching/WhyThisWorkout";
import { EmptyState, ErrorState, Skeleton, StaleDataState } from "@/components/coaching/ui-states";
import { useTodayDashboard } from "@/hooks/useCoachingDashboard";
import { oneSentenceSummary, reasonLabel } from "@/lib/coachingLabels";
import Link from "next/link";

function todayOffsetFromIso(iso?: string): number {
  if (!iso) return new Date().getDay() === 0 ? 6 : new Date().getDay() - 1;
  const d = new Date(`${iso}T12:00:00`);
  const day = d.getDay();
  return day === 0 ? 6 : day - 1;
}

export default function TodayPage() {
  const { data, isLoading, isError, error, refetch, isFetching } = useTodayDashboard();
  const brief = data?.brief;
  const freshness = data?.data_freshness || brief?.data_freshness || {};
  const staleMetrics = Object.values(freshness).filter(
    (f) => f && (f.status === "stale" || f.freshness === "stale")
  );

  if (isLoading) {
    return (
      <div className="space-y-2.5" aria-busy="true" aria-label="Laster dagens coaching">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-36 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  if (isError) {
    return (
      <ErrorState
        title="Kunne ikke hente dagens anbefaling"
        description={error instanceof Error ? error.message : "Backend svarte ikke"}
        onRetry={() => refetch()}
      />
    );
  }

  if (!brief) {
    return (
      <EmptyState
        title="Ingen coachingdata ennå"
        description="Synkroniser aktiviteter eller åpne systemet for å sjekke datakvalitet."
        action={
          <Link href="/system" className="text-sm font-medium text-status-info underline">
            Gå til system
          </Link>
        }
      />
    );
  }

  const sentence = oneSentenceSummary({
    workoutType: brief.recommendation?.workout_type,
    decisionStatus: brief.recommendation?.decision_status,
    recoveryTrend: brief.athlete_state_summary?.recovery?.trend,
  });

  const adapted = (brief as { plan_adaptation?: { plan_status?: string } }).plan_adaptation
    ?.plan_status
    ? (brief as { plan_adaptation?: { plan_status?: string } }).plan_adaptation?.plan_status !==
      "keep"
    : false;

  return (
    <div className="space-y-3">
      <header className="space-y-0.5">
        <p className="text-[10px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
          {data?.date || "I dag"}
          {isFetching ? " · oppdaterer…" : ""}
        </p>
        <h1 className="max-w-3xl text-xl font-semibold tracking-tight text-foreground md:text-2xl">
          {sentence}
        </h1>
        <p className="text-xs text-muted-foreground">Fra coaching-motoren — ikke lokal frontend-logikk.</p>
      </header>

      {data?.system_attention ? (
        <StaleDataState
          message={
            (data.system_issues || []).slice(0, 2).map((c) => reasonLabel(c) || c).join(" · ") ||
            "Noen treningsdata krever oppmerksomhet"
          }
        />
      ) : null}

      {staleMetrics.length > 0 ? (
        <StaleDataState message="Terskel eller andre nøkkeldata er gamle — tilliten er redusert." />
      ) : null}

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-5">
        <div className="space-y-3 lg:col-span-3">
          <AthleteStateCard state={brief.athlete_state_summary} />
          <NextWorkoutCard
            recommendation={brief.recommendation}
            prescription={brief.workout_prescription}
          />
          <WhyThisWorkout
            reasons={brief.why}
            explanation={brief.decision_explanation}
            guardrails={brief.guardrails}
          />
        </div>
        <div className="space-y-3 lg:col-span-2">
          <WeeklyTrainingPlan
            plan={brief.plan}
            todayOffset={todayOffsetFromIso(data?.date)}
            adjusted={adapted}
          />
          <FormTrendStrip state={brief.athlete_state_summary} />
          {(brief.warnings || []).length > 0 ? (
            <section className="rounded-xl border border-status-warning/30 bg-status-warning/5 px-3 py-2">
              <h2 className="text-xs font-semibold text-foreground">Å følge med på</h2>
              <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-muted-foreground">
                {(brief.warnings || []).slice(0, 5).map((w) => (
                  <li key={w}>{reasonLabel(w)}</li>
                ))}
              </ul>
              <Link href="/system" className="mt-1.5 inline-block text-xs text-status-info underline">
                Diagnostikk
              </Link>
            </section>
          ) : null}
        </div>
      </div>
    </div>
  );
}
