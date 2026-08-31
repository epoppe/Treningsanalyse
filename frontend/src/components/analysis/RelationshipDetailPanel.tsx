"use client";

import Link from "next/link";
import type { RelationshipCardData } from "@/types/analysis";
import { useRelationshipLag, useTimeseries } from "@/hooks/useAnalysisWorkspace";
import { LagChart } from "./LagChart";
import { AnalysisSkeleton, EvidenceBadge } from "./ui";
import {
  Line,
  LineChart,
  ResponsiveContainer,
} from "recharts";
import { ANALYSIS_CHART_COLORS, CHART_LINE, CHART_MARGIN } from "@/components/charts/chartTheme";
import {
  ThemedCartesianGrid,
  ThemedLegend,
  ThemedTooltip,
  ThemedXAxis,
  ThemedYAxis,
} from "@/components/charts/ThemedRecharts";
import {
  formatChartAxisDate,
  formatChartTooltipDate,
  formatWithUnit,
} from "@/lib/chartFormatters";
import { getAnalysisMetricLabel } from "@/lib/metrics";

function mapOutcomeMetric(outcome: string): string | null {
  const map: Record<string, string> = {
    easy_efficiency: "fitness.ef_30d",
    threshold_pace: "running.critical_speed",
    durability: "running.durability_score",
    hrv: "cardio.hrv_7d",
    ef: "fitness.ef_30d",
    critical_speed: "running.critical_speed",
  };
  if (outcome.includes(".")) return outcome;
  return map[outcome] || null;
}

function mapStimulusMetric(stimulus: string): string | null {
  const map: Record<string, string> = {
    easy_volume: "stimulus.easy_volume",
    threshold_volume: "stimulus.threshold_volume",
    high_intensity_volume: "stimulus.vo2_volume",
    weekly_tss: "stimulus.weekly_tss",
    long_run_volume: "stimulus.long_run_volume",
  };
  if (stimulus.includes(".")) return stimulus;
  return map[stimulus] || null;
}

function humanizeKey(key: string): string {
  return getAnalysisMetricLabel(key) || key.replace(/_/g, " ");
}

function associationLabel(value?: string | null): string {
  if (!value) return "—";
  const map: Record<string, string> = {
    positive: "Positiv",
    negative: "Negativ",
    neutral: "Nøytral",
    mixed: "Blandet",
  };
  return map[value.toLowerCase()] || value.replace(/_/g, " ");
}

function AlignedTimeline({ metrics, period }: { metrics: string[]; period: string }) {
  const ts = useTimeseries(period, metrics.slice(0, 2));
  if (ts.isLoading) return <AnalysisSkeleton className="mt-2 h-36" />;
  if (!ts.data?.series) {
    return <p className="mt-2 text-[11px] text-slate-500">Ingen aligned tidsserie for dette paret.</p>;
  }

  const keys = Object.keys(ts.data.series);
  const byDate = new Map<string, Record<string, number | string>>();
  keys.forEach((key) => {
    for (const p of ts.data!.series[key].points) {
      const row = byDate.get(p.date) || { date: p.date };
      row[key] = p.value;
      byDate.set(p.date, row);
    }
  });
  const rows = Array.from(byDate.values()).sort((a, b) =>
    String(a.date).localeCompare(String(b.date)),
  );
  if (!rows.length) {
    return <p className="mt-2 text-[11px] text-slate-500">Ingen aligned tidsserie for dette paret.</p>;
  }

  const labels = Object.fromEntries(
    keys.map((key) => [key, getAnalysisMetricLabel(key, ts.data?.series[key])]),
  );

  return (
    <div className="mt-2 h-40 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={CHART_MARGIN.compact}>
          <ThemedCartesianGrid />
          <ThemedXAxis
            dataKey="date"
            minTickGap={28}
            tickFormatter={(v) => formatChartAxisDate(String(v), "dayMonth")}
          />
          <ThemedYAxis width={36} />
          <ThemedTooltip
            labelFormatter={(label) => formatChartTooltipDate(String(label))}
            formatter={(value: any, name: any) => {
              const key = String(name);
              const unit = ts.data?.series[key]?.unit || "";
              return [
                unit ? formatWithUnit(Number(value), unit, 1) : String(value),
                labels[key] || key,
              ];
            }}
          />
          <ThemedLegend formatter={(value) => labels[String(value)] || String(value)} />
          {keys.map((key, i) => (
            <Line
              key={key}
              type="monotone"
              dataKey={key}
              name={labels[key] || key}
              stroke={ANALYSIS_CHART_COLORS[i % ANALYSIS_CHART_COLORS.length]}
              strokeWidth={CHART_LINE.strokeWidth}
              dot={false}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function RelationshipDetailPanel({
  card,
  period,
}: {
  card: RelationshipCardData;
  period: string;
}) {
  const lag = useRelationshipLag(
    card.stimulus,
    card.outcome,
    period,
    Boolean(card.stimulus && card.outcome),
  );
  const outcomeMetric = mapOutcomeMetric(card.outcome);
  const stimulusMetric = mapStimulusMetric(card.stimulus);
  const alignedMetrics = [stimulusMetric, outcomeMetric].filter(Boolean) as string[];

  return (
    <div className="mt-3 space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="rounded-md border border-amber-200 bg-amber-50 px-2 py-1.5 text-[11px] text-amber-900">
        Observasjonell assosiasjon — sammenheng over tid, ikke årsakssammenheng.
      </div>

      <dl className="grid gap-1 text-xs text-slate-700 sm:grid-cols-2">
        <div className="flex justify-between gap-2">
          <dt className="text-slate-500">Stimulus</dt>
          <dd className="font-medium">{humanizeKey(card.stimulus)}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-slate-500">Utfall</dt>
          <dd className="font-medium">{humanizeKey(card.outcome)}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-slate-500">Best støttet lag</dt>
          <dd className="font-medium">
            {lag.data?.best_lag_days ?? card.lag_days ?? "—"}
            {(lag.data?.best_lag_days ?? card.lag_days) != null ? " dager" : ""}
          </dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-slate-500">Retning / effekt</dt>
          <dd className="font-medium">
            {associationLabel(card.association)}
            {card.effect != null ? ` · ${card.effect}` : ""}
          </dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-slate-500">Antall observasjoner</dt>
          <dd className="font-medium">{card.sample_count}</dd>
        </div>
        <div className="flex items-center justify-between gap-2">
          <dt className="text-slate-500">Evidens</dt>
          <dd>
            <EvidenceBadge evidence={card.evidence} />
          </dd>
        </div>
      </dl>

      <div>
        <p className="text-xs font-semibold text-slate-800">1. Lag-profil</p>
        {lag.isLoading ? <AnalysisSkeleton className="mt-2 h-32" /> : null}
        {lag.data ? <LagChart data={lag.data} /> : null}
      </div>

      <div>
        <p className="text-xs font-semibold text-slate-800">2. Alignet tidslinje (stimulus / utfall)</p>
        {alignedMetrics.length >= 2 ? (
          <AlignedTimeline metrics={alignedMetrics} period={period} />
        ) : (
          <p className="mt-1 text-[11px] text-slate-500">
            Tidsserie ikke tilgjengelig for dette paret i workspace-katalogen.
          </p>
        )}
      </div>

      <div>
        <p className="text-xs font-semibold text-slate-800">3. Scatter (avansert)</p>
        <Link href="/sammenhenger" className="mt-1 inline-block text-xs font-medium text-slate-800 underline">
          Åpne avansert scatter på /sammenhenger
        </Link>
      </div>
    </div>
  );
}
