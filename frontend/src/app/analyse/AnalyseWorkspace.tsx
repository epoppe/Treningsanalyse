"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import {
  AnalysisFiltersBar,
  AnalysisTabs,
  useAnalysisUrlState,
} from "@/components/analysis/AnalysisShell";
import { AnalysisPresets } from "@/components/analysis/AnalysisPresets";
import { BestPeriodBacktracePanel } from "@/components/analysis/BestPeriodBacktracePanel";
import { DevelopmentTimeline } from "@/components/analysis/DevelopmentTimeline";
import {
  DurationCurvePanel,
  IntensityDistributionPanel,
} from "@/components/analysis/DurationCurvePanel";
import { HistoryTimeline } from "@/components/analysis/HistoryTimeline";
import { WeekExplorer } from "@/components/analysis/WeekExplorer";
import { MetricPicker } from "@/components/analysis/MetricPicker";
import { PeriodComparison } from "@/components/analysis/PeriodComparison";
import { RelationshipCard } from "@/components/analysis/RelationshipCard";
import { RelationshipMatrixView } from "@/components/analysis/RelationshipMatrixView";
import { TrainingResponsePanel } from "@/components/analysis/TrainingResponsePanel";
import { TrendSummaryCard } from "@/components/analysis/TrendSummaryCard";
import {
  AnalysisEmpty,
  AnalysisError,
  AnalysisSkeleton,
} from "@/components/analysis/ui";
import {
  useAnalysisCatalog,
  useBestPeriodBacktrace,
  useDevelopment,
  useDurationCurveHistory,
  useHistory,
  useIntensityDistribution,
  usePeriodComparison,
  useRelationshipMatrix,
  useRelationships,
  useTimeseries,
  useTrainingResponse,
  useWeekExplorer,
} from "@/hooks/useAnalysisWorkspace";
import type { AnalysisPreset } from "@/types/analysis";

const DEFAULT_METRICS = ["fitness.ctl", "cardio.hrv_7d", "fitness.ef_30d", "running.durability_score"];

function UtviklingPanel() {
  const { state, setParams } = useAnalysisUrlState();
  const catalog = useAnalysisCatalog();
  const development = useDevelopment(state.period);
  const timeseries = useTimeseries(state.period, state.metrics);
  // Stagger heavy secondary fetches until primary development settles — reduces
  // SQLite contention when many analysis endpoints hit the DB at once.
  const secondaryReady = !development.isLoading && !development.isFetching;
  const comparison = usePeriodComparison(state.period, secondaryReady);
  const intensity = useIntensityDistribution(state.period, secondaryReady);
  const durationCurve = useDurationCurveHistory(state.period, secondaryReady);
  const backtrace = useBestPeriodBacktrace(
    state.period === "28d" ? "2y" : state.period,
    state.backtrace,
    secondaryReady
  );

  const toggleMetric = (metric: string) => {
    const set = new Set(state.metrics);
    if (set.has(metric)) {
      if (set.size <= 1) return;
      set.delete(metric);
    } else if (set.size < 4) {
      set.add(metric);
    }
    setParams({ metrics: Array.from(set).join(",") });
  };

  const metrics = catalog.data?.metrics || [];

  return (
    <div className="space-y-4">
      <section>
        <h2 className="text-sm font-semibold text-slate-900">Utviklingssammendrag</h2>
        <p className="mt-0.5 text-xs text-slate-500">
          Stimulus → restitusjon → adaptasjon — hvordan utvikler nøkkelområder seg?
        </p>
        {development.isLoading ? (
          <div className="mt-2 grid grid-cols-2 gap-2 md:grid-cols-3 lg:grid-cols-4">
            {Array.from({ length: 7 }).map((_, i) => (
              <AnalysisSkeleton key={i} className="h-24" />
            ))}
          </div>
        ) : null}
        {development.isError ? (
          <div className="mt-2">
            <AnalysisError
              title="Kunne ikke hente utvikling"
              description={
                development.error instanceof Error ? development.error.message : undefined
              }
              onRetry={() => development.refetch()}
            />
          </div>
        ) : null}
        {development.data ? (
          <div className="mt-2 grid grid-cols-2 gap-2 md:grid-cols-3 lg:grid-cols-4">
            {development.data.domains.map((d) => (
              <TrendSummaryCard key={d.domain} domain={d} />
            ))}
          </div>
        ) : null}
        {development.data?.disclaimer ? (
          <p className="mt-2 text-[11px] text-slate-500">{development.data.disclaimer}</p>
        ) : null}
      </section>

      <div className="grid gap-3 lg:grid-cols-[240px_1fr]">
        <MetricPicker metrics={metrics} selected={state.metrics} onToggle={toggleMetric} />
        <DevelopmentTimeline
          data={timeseries.data}
          selected={state.metrics}
          onToggleMetric={toggleMetric}
          available={
            state.metrics.length
              ? state.metrics
              : development.data?.available_metrics?.slice(0, 8) || DEFAULT_METRICS
          }
          onSelectDate={(isoDate) =>
            setParams({ tab: "historikk", week: isoDate.slice(0, 10) })
          }
        />
      </div>
      {timeseries.isError ? (
        <AnalysisError title="Tidsserie feilet" onRetry={() => timeseries.refetch()} />
      ) : null}

      <IntensityDistributionPanel data={intensity.data} />
      <DurationCurvePanel data={durationCurve.data} />
      <BestPeriodBacktracePanel
        data={backtrace.data}
        metric={state.backtrace}
        onMetricChange={(m) => setParams({ backtrace: m })}
      />

      {comparison.isLoading ? <AnalysisSkeleton className="h-40" /> : null}
      {comparison.data ? (
        <PeriodComparison rows={comparison.data.rows} disclaimer={comparison.data.disclaimer} />
      ) : null}

      <p className="text-xs text-slate-500">
        Drill-down:{" "}
        <Link href="/vo2max" className="underline">
          VO₂max
        </Link>
        {" · "}
        <Link href="/training-stress" className="underline">
          Belastning
        </Link>
        {" · "}
        <Link href="/analytics" className="underline">
          Løpeanalyse
        </Link>
      </p>
    </div>
  );
}

function SammenhengerPanel() {
  const { state, setParams } = useAnalysisUrlState();
  const catalog = useAnalysisCatalog();
  const query = useRelationships(state.period);
  const [advanced, setAdvanced] = useState(false);
  const secondaryReady = !query.isLoading && !query.isFetching;
  const matrix = useRelationshipMatrix(state.period, advanced, secondaryReady);
  const training = useTrainingResponse(state.period, state.outcome, secondaryReady);

  const presets = catalog.data?.presets || [];

  const onSelectPreset = (preset: AnalysisPreset) => {
    const metrics = [preset.outcome, ...(preset.predictors || [])]
      .filter((k) => !k.startsWith("stimulus."))
      .slice(0, 4);
    setParams({
      tab: "sammenhenger",
      preset: preset.id,
      outcome: preset.outcome,
      metrics: metrics.join(",") || null,
    });
  };

  const bySection = useMemo(() => {
    if (!query.data?.cards?.length) return [];
    return query.data.sections.map((section) => ({
      section,
      cards: query.data!.cards.filter((c) => c.section === section),
    }));
  }, [query.data]);

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-slate-200 bg-amber-50/60 px-3 py-2 text-xs text-slate-700">
        Sammenhengene er observasjonelle (assosiert med / fulgt av) — ikke årsaksforklaringer.
        Matematisk avhengige par undertrykkes som standard.
        {query.data?.disclaimer ? ` ${query.data.disclaimer}` : ""}
      </div>

      <AnalysisPresets presets={presets} onSelect={onSelectPreset} />

      <TrainingResponsePanel
        outcome={state.outcome}
        onOutcomeChange={(key) => setParams({ outcome: key })}
        data={training.data}
        isLoading={training.isLoading}
      />

      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-slate-900">Matrise</h2>
        <label className="flex items-center gap-1.5 text-[11px] text-slate-600">
          <input
            type="checkbox"
            checked={advanced}
            onChange={(e) => setAdvanced(e.target.checked)}
          />
          Avansert (vis advarsler for delte komponenter)
        </label>
      </div>
      {matrix.isLoading ? <AnalysisSkeleton className="h-40" /> : null}
      {matrix.data ? (
        <RelationshipMatrixView
          predictors={matrix.data.predictors}
          outcomes={matrix.data.outcomes}
          cells={matrix.data.cells}
          disclaimer={matrix.data.disclaimer}
        />
      ) : null}

      {query.isLoading ? (
        <div className="grid gap-2 md:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <AnalysisSkeleton key={i} className="h-32" />
          ))}
        </div>
      ) : null}
      {query.isError ? (
        <AnalysisError title="Kunne ikke hente sammenhenger" onRetry={() => query.refetch()} />
      ) : null}
      {!query.isLoading && !query.isError && !query.data?.cards?.length ? (
        <AnalysisEmpty title="Ingen sammenhenger" description="Backend returnerte ingen kort." />
      ) : null}

      {bySection.map((group) => (
        <section key={group.section} className="space-y-2">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            {group.section}
          </h2>
          <div className="grid gap-2 md:grid-cols-2">
            {group.cards.map((card) => (
              <RelationshipCard key={card.id} card={card} period={state.period} />
            ))}
          </div>
        </section>
      ))}
      <p className="text-xs text-slate-500">
        Avansert manuell X/Y:{" "}
        <Link href="/sammenhenger" className="underline">
          /sammenhenger
        </Link>
      </p>
    </div>
  );
}

function HistorikkPanel() {
  const { state, setParams } = useAnalysisUrlState();
  const historyPeriod =
    state.period === "28d" || state.period === "90d" ? "2y" : state.period;
  const query = useHistory(historyPeriod);
  const weekQuery = useWeekExplorer(state.week || undefined);

  if (query.isLoading) return <AnalysisSkeleton className="h-64" />;
  if (query.isError) {
    return <AnalysisError title="Kunne ikke hente historikk" onRetry={() => query.refetch()} />;
  }
  if (!query.data) {
    return <AnalysisEmpty title="Ingen historikk" />;
  }

  return (
    <div className="space-y-3">
      <header>
        <h2 className="text-sm font-semibold text-slate-900">Treningshistorikk</h2>
        <p className="text-xs text-slate-500">
          År → måned → uke. Klikk en dato i Utvikling-grafen for ukeutforsker.
        </p>
      </header>
      {state.week ? (
        <WeekExplorer
          data={weekQuery.data}
          isLoading={weekQuery.isLoading}
          onPreviousWeek={(weekStart) => setParams({ week: weekStart })}
        />
      ) : null}
      <HistoryTimeline data={query.data} />
      <p className="text-xs text-slate-500">
        Volum/YoY:{" "}
        <Link href="/statistikk" className="underline">
          /statistikk
        </Link>
      </p>
    </div>
  );
}

export default function AnalyseWorkspace() {
  const { state } = useAnalysisUrlState();

  return (
    <div className="mx-auto max-w-6xl space-y-4 px-3 py-4 md:px-4">
      <header className="space-y-1">
        <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
          Analyseworkspace
        </p>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Analyse</h1>
        <p className="max-w-2xl text-sm text-slate-600">
          Kuratert longitudinell analyse: stimulus → restitusjon → adaptasjon → prestasjon — uten
          å flate ut hele MCP-katalogen.
        </p>
      </header>

      <AnalysisFiltersBar />
      <AnalysisTabs />

      {state.tab === "utvikling" ? <UtviklingPanel /> : null}
      {state.tab === "sammenhenger" ? <SammenhengerPanel /> : null}
      {state.tab === "historikk" ? <HistorikkPanel /> : null}
    </div>
  );
}
