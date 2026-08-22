"use client";

import Link from "next/link";
import { AthleteStateCard } from "@/components/cockpit/AthleteStateCard";
import { DevelopmentStrip, WeeklyPlanStrip } from "@/components/cockpit/WeeklyPlanStrip";
import { NextWorkoutCard } from "@/components/cockpit/NextWorkoutCard";
import { WhyThisWorkout } from "@/components/cockpit/WhyThisWorkout";
import { AnalysisError, AnalysisSkeleton } from "@/components/analysis/ui";
import { formatNorwegianDate, warningLabel } from "@/components/cockpit/cockpitUtils";
import { SinceLastUpdate } from "@/components/cockpit/SinceLastUpdate";
import { useCockpitSync } from "@/components/cockpit/CockpitSyncProvider";
import { InsightFeed } from "@/components/cockpit/InsightFeed";
import { ConnectionStatus } from "@/components/cockpit/ConnectionStatus";
import { useWhatChanged } from "@/hooks/useDashboard";
import { useHighlights } from "@/hooks/useAnalysisWorkspace";
import { useTodayDashboard } from "@/hooks/useTodayDashboard";

export default function TodayCockpitPage() {
  const query = useTodayDashboard();
  const whatChangedQuery = useWhatChanged(false);
  const highlights = useHighlights("1y");
  const { lastWhatChanged, postSyncSummary } = useCockpitSync();
  const data = query.data;
  const whatChanged = lastWhatChanged || whatChangedQuery.data;

  if (query.isLoading) {
    return (
      <div className="space-y-4">
        <AnalysisSkeleton className="h-8 w-48" />
        <AnalysisSkeleton className="h-28 w-full" />
        <AnalysisSkeleton className="h-64 w-full" />
        <AnalysisSkeleton className="h-48 w-full" />
      </div>
    );
  }

  if (query.isError || !data) {
    return (
      <AnalysisError
        title="Treningsanalyse-serveren er ikke tilgjengelig."
        description={query.error instanceof Error ? query.error.message : undefined}
        onRetry={() => query.refetch()}
      />
    );
  }

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
            I dag
          </p>
          <ConnectionStatus online={!query.isError} asOf={data.as_of} />
        </div>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900 capitalize">
          {formatNorwegianDate(data.as_of)}
        </h1>
        {data.training_phase?.phase ? (
          <p className="text-sm text-slate-600">
            Fase: {String(data.training_phase.phase)}
            {data.goal?.target_event ? ` · Mål: ${String(data.goal.target_event)}` : ""}
          </p>
        ) : null}
      </header>

      <AthleteStateCard state={data.athlete_state} />

      <SinceLastUpdate whatChanged={whatChanged} postSync={postSyncSummary} />

      <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
        <NextWorkoutCard data={data} />
        <WhyThisWorkout
          explanation={data.decision_explanation}
          fallbackReasons={data.why}
          workoutType={data.recommendation?.workout_type}
          asOfDate={data.as_of}
        />
      </div>

      {data.warnings && data.warnings.length > 0 ? (
        <section className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          {data.warnings.slice(0, 3).map((warning) => (
            <p key={warning}>{warningLabel(warning)}</p>
          ))}
        </section>
      ) : null}

      <WeeklyPlanStrip data={data} />
      <InsightFeed data={highlights.data} />
      <DevelopmentStrip data={data} />

      <div className="flex flex-wrap gap-3 text-sm">
        <Link href="/analyse" className="font-medium text-slate-900 underline">
          Åpne analyse
        </Link>
        <Link href="/aktiviteter" className="text-slate-600 underline">
          Se aktiviteter
        </Link>
        <Link href="/synkronisering" className="text-slate-600 underline">
          Synkroniser data
        </Link>
      </div>
    </div>
  );
}
