"use client";

import Link from "next/link";
import { WeeklyTrainingPlan } from "@/components/coaching/WeeklyTrainingPlan";
import { EmptyState, ErrorState, Skeleton, StatusBadge } from "@/components/coaching/ui-states";
import { usePlanSummary } from "@/hooks/useCoachingDashboard";
import { workoutLabel } from "@/lib/coachingLabels";

function phaseLabel(phase: unknown): string | null {
  if (phase == null) return null;
  if (typeof phase === "string") return phase;
  if (typeof phase === "object" && phase !== null && "phase" in phase) {
    const p = (phase as { phase?: unknown }).phase;
    return typeof p === "string" ? p : null;
  }
  return null;
}

function goalSummary(goal: Record<string, unknown> | null | undefined): string {
  if (!goal) return "";
  const event =
    (typeof goal.event === "string" && goal.event) ||
    (typeof goal.target_event === "string" && goal.target_event) ||
    (typeof goal.goal_type === "string" && goal.goal_type.replace(/_/g, " ")) ||
    null;
  const date = typeof goal.target_date === "string" ? goal.target_date : null;
  const feasibility =
    goal.goal_feasibility &&
    typeof goal.goal_feasibility === "object" &&
    goal.goal_feasibility !== null &&
    "status" in goal.goal_feasibility
      ? String((goal.goal_feasibility as { status?: string }).status)
      : null;
  return [event, date, feasibility].filter(Boolean).join(" · ");
}

export default function PlanPage() {
  const { data, isLoading, isError, error, refetch } = usePlanSummary();

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-56" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }
  if (isError) {
    return (
      <ErrorState
        title="Kunne ikke hente plan"
        description={error instanceof Error ? error.message : undefined}
        onRetry={() => refetch()}
      />
    );
  }
  if (!data?.plan) {
    return (
      <EmptyState
        title="Ingen ukeplan ennå"
        description="Planen bygges når coaching-motoren har nok data."
      />
    );
  }

  const phase = phaseLabel(data.training_phase) || phaseLabel(data.training_phase_detail);
  const detail = data.training_phase_detail;
  const objectives = detail?.primary_objectives || [];
  const stability =
    typeof data.plan_stability === "string" ? data.plan_stability.replace(/_/g, " ") : null;
  const goalText = goalSummary(data.goal as Record<string, unknown> | null);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">Plan</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Ukeplan og fase — detaljerte metrikk-sider ligger som drill-down.
        </p>
      </header>

      <div className="flex flex-wrap gap-2">
        {phase ? <StatusBadge status="info" label={`Fase: ${phase}`} /> : null}
        {stability ? <StatusBadge status="neutral" label={`Stabilitet: ${stability}`} /> : null}
      </div>

      {objectives.length > 0 ? (
        <p className="text-sm text-muted-foreground">
          Fokus: {objectives.map((o) => workoutLabel(o) === o ? o : o).join(" · ")}
        </p>
      ) : null}

      {goalText ? (
        <section className="rounded-2xl border border-border bg-surface p-5">
          <h2 className="text-lg font-semibold">Mål</h2>
          <p className="mt-2 text-sm text-muted-foreground">{goalText}</p>
        </section>
      ) : (
        <EmptyState title="Ingen mål satt" description="Planen følger generelle treningsfaser." />
      )}

      <WeeklyTrainingPlan plan={data.plan} />

      <section className="rounded-2xl border border-border bg-surface p-5">
        <h2 className="text-lg font-semibold">Treningsblokk</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Mesosyklus-visning kommer som kompakt volum/fokus per uke. Bruk ukeplanen over for
          nærmeste dager.
        </p>
        <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {["Base", "Build", "Build", "Recovery"].map((blockPhase, i) => (
            <div key={`${blockPhase}-${i}`} className="rounded-xl bg-surface-muted px-3 py-4 text-center">
              <p className="text-xs text-muted-foreground">Uke {i + 1}</p>
              <p className="mt-1 font-medium">{blockPhase}</p>
            </div>
          ))}
        </div>
      </section>

      <p className="text-sm text-muted-foreground">
        Se også{" "}
        <Link href="/training-status" className="underline">
          treningstatus
        </Link>
        .
      </p>
    </div>
  );
}
