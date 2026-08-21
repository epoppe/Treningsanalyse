"use client";

import Link from "next/link";
import { WeeklyTrainingPlan } from "@/components/coaching/WeeklyTrainingPlan";
import { EmptyState, ErrorState, Skeleton, StatusBadge } from "@/components/coaching/ui-states";
import { usePlanSummary } from "@/hooks/useCoachingDashboard";

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

  const goal = data.goal as { event?: string; target?: string; date?: string } | null;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">Plan</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Ukeplan og fase — detaljerte metrikk-sider ligger som drill-down.
        </p>
      </header>

      <div className="flex flex-wrap gap-2">
        {data.training_phase ? <StatusBadge status="info" label={`Fase: ${data.training_phase}`} /> : null}
        {data.plan_stability ? (
          <StatusBadge status="neutral" label={`Stabilitet: ${data.plan_stability}`} />
        ) : null}
      </div>

      {goal ? (
        <section className="rounded-2xl border border-border bg-surface p-5">
          <h2 className="text-lg font-semibold">Mål</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            {[goal.event, goal.target, goal.date].filter(Boolean).join(" · ") ||
              "Mål konfigurert — se detaljer i backend goal context."}
          </p>
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
          {["Base", "Build", "Build", "Recovery"].map((phase, i) => (
            <div key={`${phase}-${i}`} className="rounded-xl bg-surface-muted px-3 py-4 text-center">
              <p className="text-xs text-muted-foreground">Uke {i + 1}</p>
              <p className="mt-1 font-medium">{phase}</p>
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
