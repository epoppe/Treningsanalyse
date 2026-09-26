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
  groupSeriesByUnit,
  insertGapNulls,
  seriesShowsGaps,
  type TimelineSeriesMeta,
} from "@/lib/timelineSeries";
import {
  axisLabelProps,
  formatChartAxisDate,
  formatChartTooltipDate,
  formatWithUnit,
} from "@/lib/chartFormatters";
import { getAnalysisMetricLabel } from "@/lib/metrics";

const COLORS = [...ANALYSIS_CHART_COLORS];

function seriesRows(payload: TimeseriesPayload, keys: string[]) {
  const byDate = new Map<string, Record<string, number | string | null>>();
  keys.forEach((key) => {
    const meta = payload.series[key] as TimelineSeriesMeta | undefined;
    const showGaps = seriesShowsGaps(meta);
    const points = insertGapNulls(payload.series[key].points || [], showGaps);
    for (const point of points) {
      const row = byDate.get(point.date) || { date: point.date };
      row[key] = point.value;
      byDate.set(point.date, row);
    }
  });
  return Array.from(byDate.values()).sort((a, b) => String(a.date).localeCompare(String(b.date)));
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
  const keys = data ? Object.keys(data.series) : selected;
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const seriesMeta = useMemo(() => {
    const meta: Record<string, { label: string; unit: string; showGaps: boolean }> = {};
    keys.forEach((key) => {
      const s = data?.series[key];
      meta[key] = {
        label: getAnalysisMetricLabel(key, s),
        unit: s?.unit || s?.unit_note || "",
        showGaps: seriesShowsGaps(s),
      };
    });
    return meta;
  }, [data, keys]);

  const unitGroups = useMemo(() => groupSeriesByUnit(keys, seriesMeta), [keys, seriesMeta]);
  const panelRows = useMemo(() => {
    if (!data) return unitGroups.map(() => []);
    return unitGroups.map((group) => seriesRows(data, group));
  }, [data, unitGroups]);
  const hasAnyPoints = panelRows.some((panel) => panel.length > 0);

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
      <div className="mt-3 space-y-3">
        {!hasAnyPoints ? (
          <p className="flex h-64 items-center justify-center text-xs text-slate-500">
            Ingen tidsseriedata for valgt periode.
          </p>
        ) : (
          unitGroups.map((group, groupIndex) => {
            const groupRows = panelRows[groupIndex] || [];
            const unit = seriesMeta[group[0]]?.unit || "";
            const hasMeasuredGap = groupRows.some((row) =>
              group.some((key) => row[key] == null),
            );
            const isLast = groupIndex === unitGroups.length - 1;
            return (
              <div key={unit || group.join("-")} data-unit-panel={unit || "ukjent"}>
                <p className="mb-1 text-[11px] font-medium text-slate-600">
                  {unit || "Ukjent enhet"}
                  {unitGroups.length > 1 ? " · eget panel" : ""}
                  {hasMeasuredGap ? " · hull er manglende målinger" : ""}
                </p>
                <div className="h-52 w-full">
                {groupRows.length === 0 ? (
                  <p className="flex h-full items-center justify-center text-xs text-slate-500">
                    Ingen målinger i {unit || "denne enheten"} for valgt periode.
                  </p>
                ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart
                    data={groupRows}
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
                    <ThemedYAxis width={44} unit={unit ? ` ${unit}` : undefined} />
                    <ThemedTooltip
                      labelFormatter={(label) => formatChartTooltipDate(String(label))}
                      formatter={(value: any, name: any) => {
                        const meta = seriesMeta[String(name)];
                        const formatted =
                          value == null
                            ? "mangler"
                            : meta?.unit
                              ? formatWithUnit(Number(value), meta.unit, 1)
                              : String(value);
                        return [formatted, meta?.label || String(name)];
                      }}
                    />
                    <ThemedLegend
                      formatter={(value) => seriesMeta[String(value)]?.label || String(value)}
                    />
                    {group.map((key) => (
                      <Line
                        key={key}
                        type="monotone"
                        dataKey={key}
                        name={seriesMeta[key]?.label || key}
                        stroke={COLORS[keys.indexOf(key) % COLORS.length]}
                        dot={CHART_LINE.dot}
                        strokeWidth={CHART_LINE.strokeWidth}
                        connectNulls={!seriesMeta[key]?.showGaps}
                      />
                    ))}
                    {isLast ? (
                      <Brush
                        dataKey="date"
                        height={22}
                        stroke="#334155"
                        travellerWidth={8}
                        startIndex={
                          rangeFrom
                            ? Math.max(0, groupRows.findIndex((row) => String(row.date) >= rangeFrom))
                            : undefined
                        }
                        endIndex={
                          rangeTo
                            ? groupRows.reduce(
                                (found, row, index) => (String(row.date) <= rangeTo ? index : found),
                                groupRows.length - 1,
                              )
                            : undefined
                        }
                        tickFormatter={(v) => formatChartAxisDate(String(v), "dayMonth")}
                        onChange={(range) => {
                          if (!onRangeSelect || !range) return;
                          const startIndex = range.startIndex;
                          const endIndex = range.endIndex;
                          if (startIndex == null || endIndex == null) return;
                          const from = groupRows[startIndex]?.date;
                          const to = groupRows[endIndex]?.date;
                          if (!from || !to) return;
                          if (debounceRef.current) clearTimeout(debounceRef.current);
                          debounceRef.current = setTimeout(() => {
                            onRangeSelect(String(from), String(to));
                          }, 250);
                        }}
                      />
                    ) : null}
                  </LineChart>
                </ResponsiveContainer>
                )}
                </div>
              </div>
            );
          })
        )}
      </div>
      {data?.note ? <p className="mt-2 text-[11px] text-slate-500">{data.note}</p> : null}
    </section>
  );
}
