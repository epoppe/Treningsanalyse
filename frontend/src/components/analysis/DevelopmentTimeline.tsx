"use client";

import {
  Line,
  LineChart,
  ResponsiveContainer,
} from "recharts";
import type { TimeseriesPayload } from "@/types/analysis";
import { ANALYSIS_CHART_COLORS, CHART_LINE, CHART_MARGIN } from "@/components/charts/chartTheme";
import {
  ThemedCartesianGrid,
  ThemedTooltip,
  ThemedXAxis,
  ThemedYAxis,
} from "@/components/charts/ThemedRecharts";

const COLORS = [...ANALYSIS_CHART_COLORS];

function mergeSeries(payload: TimeseriesPayload) {
  const keys = Object.keys(payload.series);
  const byDate = new Map<string, Record<string, number | string>>();
  keys.forEach((key) => {
    for (const p of payload.series[key].points) {
      const row = byDate.get(p.date) || { date: p.date };
      row[key] = p.value;
      byDate.set(p.date, row);
    }
  });
  return { keys, rows: Array.from(byDate.values()).sort((a, b) => String(a.date).localeCompare(String(b.date))) };
}

export function DevelopmentTimeline({
  data,
  selected,
  onToggleMetric,
  available,
  onSelectDate,
}: {
  data?: TimeseriesPayload;
  selected: string[];
  onToggleMetric: (metric: string) => void;
  available: string[];
  onSelectDate?: (isoDate: string) => void;
}) {
  const { keys, rows } = data ? mergeSeries(data) : { keys: selected, rows: [] };

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-slate-900">Utvikling over tid</h2>
        <p className="text-[11px] text-slate-500">Inntil 4 metrikker · klikk i grafen for ukeutforsker</p>
      </div>
      <div className="mt-2 flex flex-wrap gap-1">
        {available.map((m) => {
          const on = selected.includes(m);
          return (
            <button
              key={m}
              type="button"
              onClick={() => onToggleMetric(m)}
              className={
                on
                  ? "rounded-md bg-slate-900 px-2 py-1 text-[11px] font-medium text-white"
                  : "rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-[11px] text-slate-700"
              }
            >
              {m}
            </button>
          );
        })}
      </div>
      <div className="mt-3 h-56 w-full">
        {rows.length === 0 ? (
          <p className="flex h-full items-center justify-center text-xs text-slate-500">
            Ingen tidsseriedata for valgt periode.
          </p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={rows}
              margin={CHART_MARGIN.compact}
              onClick={(state) => {
                const label = state?.activeLabel;
                if (label && onSelectDate) onSelectDate(String(label));
              }}
            >
              <ThemedCartesianGrid />
              <ThemedXAxis dataKey="date" minTickGap={32} />
              <ThemedYAxis width={40} />
              <ThemedTooltip labelFormatter={(label) => String(label)} />
              {keys.map((key, i) => (
                <Line
                  key={key}
                  type="monotone"
                  dataKey={key}
                  stroke={COLORS[i % COLORS.length]}
                  dot={CHART_LINE.dot}
                  strokeWidth={CHART_LINE.strokeWidth}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
      {data?.note ? <p className="mt-2 text-[11px] text-slate-500">{data.note}</p> : null}
    </section>
  );
}
