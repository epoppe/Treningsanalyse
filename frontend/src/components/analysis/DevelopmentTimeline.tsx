"use client";

import { useMemo, useRef } from "react";
import {
  Brush,
  Line,
  LineChart,
  ResponsiveContainer,
} from "recharts";
import type { TimeseriesPayload } from "@/types/analysis";
import { ANALYSIS_CHART_COLORS, CHART_LINE, CHART_MARGIN } from "@/components/charts/chartTheme";
import {
  ThemedCartesianGrid,
  ThemedLegend,
  ThemedTooltip,
  ThemedXAxis,
  ThemedYAxis,
} from "@/components/charts/ThemedRecharts";
import { formatRangeLabel } from "@/lib/analysisRange";
import {
  axisLabelProps,
  formatChartAxisDate,
  formatChartTooltipDate,
  formatWithUnit,
} from "@/lib/chartFormatters";
import { getAnalysisMetricLabel } from "@/lib/metrics";

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
  return {
    keys,
    rows: Array.from(byDate.values()).sort((a, b) =>
      String(a.date).localeCompare(String(b.date)),
    ),
  };
}

export function DevelopmentTimeline({
  data,
  selected,
  onToggleMetric,
  available,
  onSelectDate,
  rangeFrom,
  rangeTo,
  onRangeSelect,
  onClearRange,
}: {
  data?: TimeseriesPayload;
  selected: string[];
  onToggleMetric: (metric: string) => void;
  available: string[];
  onSelectDate?: (isoDate: string) => void;
  rangeFrom?: string;
  rangeTo?: string;
  onRangeSelect?: (from: string, to: string) => void;
  onClearRange?: () => void;
}) {
  const { keys, rows } = data ? mergeSeries(data) : { keys: selected, rows: [] };
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const seriesMeta = useMemo(() => {
    const meta: Record<string, { label: string; unit: string }> = {};
    keys.forEach((key) => {
      const s = data?.series[key];
      meta[key] = {
        label: getAnalysisMetricLabel(key, s),
        unit: s?.unit || s?.unit_note || "",
      };
    });
    return meta;
  }, [data, keys]);

  const brushIndexes = useMemo(() => {
    if (!rangeFrom || !rangeTo || rows.length === 0) return undefined;
    const startIndex = rows.findIndex((r) => String(r.date) >= rangeFrom);
    const endIndex = [...rows].reverse().findIndex((r) => String(r.date) <= rangeTo);
    if (startIndex < 0 || endIndex < 0) return undefined;
    return {
      startIndex,
      endIndex: rows.length - 1 - endIndex,
    };
  }, [rangeFrom, rangeTo, rows]);

  const hasSelection = Boolean(rangeFrom && rangeTo);

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">Utvikling over tid</h2>
          <p className="text-[11px] text-slate-500">
            Inntil 4 metrikker · dra i børsten for å filtrere resten av analysen
          </p>
        </div>
        {hasSelection ? (
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-md bg-slate-100 px-2 py-1 text-[11px] font-medium text-slate-700">
              {formatRangeLabel(rangeFrom!, rangeTo!)}
            </span>
            <button
              type="button"
              onClick={onClearRange}
              className="rounded-md border border-slate-200 px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-50"
            >
              Nullstill utvalg
            </button>
          </div>
        ) : null}
      </div>
      <div className="mt-2 flex flex-wrap gap-1">
        {available.map((m) => {
          const on = selected.includes(m);
          const label = getAnalysisMetricLabel(m, data?.series[m]);
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
              {label}
            </button>
          );
        })}
      </div>
      <div className="mt-3 h-64 w-full">
        {rows.length === 0 ? (
          <p className="flex h-full items-center justify-center text-xs text-slate-500">
            Ingen tidsseriedata for valgt periode.
          </p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={rows}
              margin={{ ...CHART_MARGIN.compact, bottom: 8, left: 8 }}
              onClick={(state) => {
                const label = state?.activeLabel;
                if (label && onSelectDate) onSelectDate(String(label));
              }}
            >
              <ThemedCartesianGrid />
              <ThemedXAxis
                dataKey="date"
                minTickGap={32}
                tickFormatter={(v) => formatChartAxisDate(String(v), "dayMonth")}
              />
              <ThemedYAxis width={44} label={axisLabelProps("Verdi")} />
              <ThemedTooltip
                labelFormatter={(label) => formatChartTooltipDate(String(label))}
                formatter={(value: number, name: string) => {
                  const meta = seriesMeta[name];
                  const unit = meta?.unit || "";
                  const formatted = unit
                    ? formatWithUnit(Number(value), unit, 1)
                    : String(value);
                  return [formatted, meta?.label || name];
                }}
              />
              <ThemedLegend
                formatter={(value) => seriesMeta[String(value)]?.label || String(value)}
              />
              {keys.map((key, i) => (
                <Line
                  key={key}
                  type="monotone"
                  dataKey={key}
                  name={seriesMeta[key]?.label || key}
                  stroke={COLORS[i % COLORS.length]}
                  dot={CHART_LINE.dot}
                  strokeWidth={CHART_LINE.strokeWidth}
                  connectNulls
                />
              ))}
              <Brush
                dataKey="date"
                height={22}
                stroke="#334155"
                travellerWidth={8}
                startIndex={brushIndexes?.startIndex}
                endIndex={brushIndexes?.endIndex}
                tickFormatter={(v) => formatChartAxisDate(String(v), "dayMonth")}
                onChange={(range) => {
                  if (!onRangeSelect || !range) return;
                  const startIndex = range.startIndex;
                  const endIndex = range.endIndex;
                  if (startIndex == null || endIndex == null) return;
                  const from = rows[startIndex]?.date;
                  const to = rows[endIndex]?.date;
                  if (!from || !to) return;
                  if (debounceRef.current) clearTimeout(debounceRef.current);
                  debounceRef.current = setTimeout(() => {
                    onRangeSelect(String(from), String(to));
                  }, 250);
                }}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
      {data?.note ? <p className="mt-2 text-[11px] text-slate-500">{data.note}</p> : null}
    </section>
  );
}
