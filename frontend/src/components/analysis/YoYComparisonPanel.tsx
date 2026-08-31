"use client";

import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  ResponsiveContainer,
} from "recharts";
import type { YoYPayload } from "@/types/analysis";
import { yearComparisonColors, CHART_MARGIN } from "@/components/charts/chartTheme";
import {
  ThemedCartesianGrid,
  ThemedLegend,
  ThemedTooltip,
  ThemedXAxis,
  ThemedYAxis,
} from "@/components/charts/ThemedRecharts";
import { axisLabelProps } from "@/lib/chartFormatters";
import { AnalysisSkeleton } from "./ui";

type YoYMetric = "duration" | "distance" | "activities" | "tss";

const METRIC_OPTIONS: Array<{ id: YoYMetric; label: string }> = [
  { id: "duration", label: "Løpetid" },
  { id: "distance", label: "Distanse" },
  { id: "activities", label: "Antall økter" },
  { id: "tss", label: "TSS / belastning" },
];

function valueFor(
  metric: YoYMetric,
  side?: YoYPayload["rows"][number]["current"] | null,
): number {
  if (!side) return 0;
  if (metric === "duration") return (side.duration_s || 0) / 3600;
  if (metric === "distance") return (side.distance_m || 0) / 1000;
  if (metric === "tss") return side.tss || 0;
  return side.activities || 0;
}

function yAxisLabel(metric: YoYMetric) {
  if (metric === "duration") return "Tid (timer)";
  if (metric === "distance") return "Distanse (km)";
  if (metric === "tss") return "TSS";
  return "Antall økter";
}

function unitLabel(metric: YoYMetric) {
  if (metric === "duration") return "timer";
  if (metric === "distance") return "km";
  if (metric === "tss") return "TSS";
  return "økter";
}

export function YoYComparisonPanel({
  data,
  isLoading,
}: {
  data?: YoYPayload;
  isLoading?: boolean;
}) {
  const [metric, setMetric] = useState<YoYMetric>("duration");

  const chart = useMemo(() => {
    const rows = data?.rows || [];
    if (!rows.length) {
      return { bars: [] as Array<Record<string, string | number>>, currentYear: 0, previousYear: 0 };
    }
    const currentYear = rows[rows.length - 1]?.year || new Date().getFullYear();
    const previousYear = currentYear - 1;
    const bars = rows.map((row) => ({
      label: row.month_label || `${row.month}`,
      [String(currentYear)]: valueFor(metric, row.current),
      [String(previousYear)]: valueFor(metric, row.previous_year),
    }));
    return { bars, currentYear, previousYear };
  }, [data, metric]);

  if (isLoading) return <AnalysisSkeleton className="h-48" />;
  if (!chart.bars.length) {
    return <p className="text-sm text-slate-500">Ingen YoY-data tilgjengelig.</p>;
  }

  const colors = yearComparisonColors(2);

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="text-sm font-semibold text-slate-900">År-over-år</h2>
      <p className="mt-0.5 text-[11px] text-slate-500">
        Én metrikk om gangen ({chart.previousYear} vs {chart.currentYear}). EF / durability / LT2 /
        VO2max: bruk Utvikling-fanen.
      </p>
      <div className="mt-2 flex flex-wrap gap-1">
        {METRIC_OPTIONS.map((opt) => (
          <button
            key={opt.id}
            type="button"
            onClick={() => setMetric(opt.id)}
            className={
              metric === opt.id
                ? "rounded-md bg-slate-900 px-2 py-1 text-[11px] font-medium text-white"
                : "rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-[11px] text-slate-700"
            }
          >
            {opt.label}
          </button>
        ))}
      </div>
      <div className="mt-3 h-56 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chart.bars} margin={CHART_MARGIN.compact}>
            <ThemedCartesianGrid />
            <ThemedXAxis dataKey="label" minTickGap={16} />
            <ThemedYAxis width={44} label={axisLabelProps(yAxisLabel(metric))} />
            <ThemedTooltip
              formatter={(value: any) => [
                typeof value === "number" ? value.toFixed(1) : value,
                unitLabel(metric),
              ]}
            />
            <ThemedLegend />
            <Bar
              dataKey={String(chart.previousYear)}
              fill={colors[0]}
              name={String(chart.previousYear)}
              radius={[3, 3, 0, 0]}
            />
            <Bar
              dataKey={String(chart.currentYear)}
              fill={colors[1]}
              name={String(chart.currentYear)}
              radius={[3, 3, 0, 0]}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
      {data?.disclaimer ? <p className="mt-2 text-[10px] text-slate-500">{data.disclaimer}</p> : null}
    </section>
  );
}
