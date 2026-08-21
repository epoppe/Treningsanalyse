"use client";

import Link from "next/link";
import {
  AnalysisFiltersBar,
  AnalysisTabs,
  useAnalysisUrlState,
} from "@/components/analysis/AnalysisShell";
import { DevelopmentTimeline } from "@/components/analysis/DevelopmentTimeline";
import { HistoryTimeline } from "@/components/analysis/HistoryTimeline";
import { PeriodComparison } from "@/components/analysis/PeriodComparison";
import { RelationshipCard } from "@/components/analysis/RelationshipCard";
import { TrendSummaryCard } from "@/components/analysis/TrendSummaryCard";
import {
  AnalysisEmpty,
  AnalysisError,
  AnalysisSkeleton,
} from "@/components/analysis/ui";
import {
  useDevelopment,
  useHistory,
  usePeriodComparison,
  useRelationships,
  useTimeseries,
} from "@/hooks/useAnalysisWorkspace";

const DEFAULT_METRICS = [
  "ctl",
  "hrv_rmssd",
  "easy_run_efficiency",
  "vo2max",
  "lactate_threshold_pace",
  "durability",
  "resting_hr",
  "critical_speed",
];

function UtviklingPanel() {
  const { state, setParams } = useAnalysisUrlState();
  const development = useDevelopment(state.period);
  const timeseries = useTimeseries(state.period, state.metrics);
  const comparison = usePeriodComparison(state.period);

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

  return (
    <div className="space-y-4">
      <section>
        <h2 className="text-sm font-semibold text-slate-900">Utviklingssammendrag</h2>
        <p className="mt-0.5 text-xs text-slate-500">
          Hvordan utvikler nøkkelområder seg i valgt periode?
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

      <DevelopmentTimeline
        data={timeseries.data}
        selected={state.metrics}
        onToggleMetric={toggleMetric}
        available={development.data?.available_metrics || DEFAULT_METRICS}
      />
      {timeseries.isError ? (
        <AnalysisError title="Tidsserie feilet" onRetry={() => timeseries.refetch()} />
      ) : null}

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
  const { state } = useAnalysisUrlState();
  const query = useRelationships(state.period);

  if (query.isLoading) {
    return (
      <div className="grid gap-2 md:grid-cols-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <AnalysisSkeleton key={i} className="h-32" />
        ))}
      </div>
    );
  }
  if (query.isError) {
    return <AnalysisError title="Kunne ikke hente sammenhenger" onRetry={() => query.refetch()} />;
  }
  if (!query.data?.cards?.length) {
    return <AnalysisEmpty title="Ingen sammenhenger" description="Backend returnerte ingen kort." />;
  }

  const bySection = query.data.sections.map((section) => ({
    section,
    cards: query.data!.cards.filter((c) => c.section === section),
  }));

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-slate-200 bg-amber-50/60 px-3 py-2 text-xs text-slate-700">
        Sammenhengene er observasjonelle (assosiert med / fulgt av) — ikke årsaksforklaringer.
        {query.data.disclaimer ? ` ${query.data.disclaimer}` : ""}
      </div>
      {bySection.map((group) => (
        <section key={group.section} className="space-y-2">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            {group.section}
          </h2>
          <div className="grid gap-2 md:grid-cols-2">
            {group.cards.map((card) => (
              <RelationshipCard key={card.id} card={card} />
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
  const { state } = useAnalysisUrlState();
  const historyPeriod =
    state.period === "28d" || state.period === "90d" ? "2y" : state.period;
  const query = useHistory(historyPeriod);

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
          År → måned. Ukeutforsker og blokkhistorikk kommer senere.
        </p>
      </header>
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
          Longitudinell treningsanalyse: utvikling, sammenhenger og historikk — uten å hoppe
          mellom metrikk-sider.
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
