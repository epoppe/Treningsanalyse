"use client";

import type { DurationCurvePayload, IntensityDistributionPayload } from "@/types/analysis";
import {
  CHART_MARGIN,
  chartColor,
} from "@/components/charts/chartTheme";
import {
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
} from "recharts";
import {
  ThemedCartesianGrid,
  ThemedTooltip,
  ThemedXAxis,
  ThemedYAxis,
} from "@/components/charts/ThemedRecharts";

const ZONE_COLORS = [chartColor(0), chartColor(2), chartColor(1)];

function mergeZoneSeries(payload: IntensityDistributionPayload) {
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
      String(a.date).localeCompare(String(b.date))
    ),
  };
}

export function IntensityDistributionPanel({
  data,
}: {
  data?: IntensityDistributionPayload;
}) {
  const { keys, rows } = data ? mergeZoneSeries(data) : { keys: [], rows: [] };
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-3">
      <h2 className="text-sm font-semibold text-slate-900">Intensitetsfordeling</h2>
      <p className="mt-0.5 text-[11px] text-slate-500">
        Zone 1/2/3 % over tid — nyttig for «endret fordeling før form?»
      </p>
      <div className="mt-3 h-48 w-full">
        {rows.length === 0 ? (
          <p className="flex h-full items-center justify-center text-xs text-slate-500">
            Ingen sonefordelingsdata.
          </p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={rows} margin={CHART_MARGIN.compact}>
              <ThemedCartesianGrid />
              <ThemedXAxis dataKey="date" minTickGap={40} />
              <ThemedYAxis width={36} unit="%" />
              <ThemedTooltip />
              <Legend wrapperStyle={{ fontSize: 11, color: "#475569" }} />
              {keys.map((key, i) => (
                <Line
                  key={key}
                  type="monotone"
                  dataKey={key}
                  name={key.replace("coaching.", "")}
                  stroke={ZONE_COLORS[i % ZONE_COLORS.length]}
                  dot={false}
                  strokeWidth={1.5}
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

export function DurationCurvePanel({ data }: { data?: DurationCurvePayload }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-3">
      <h2 className="text-sm font-semibold text-slate-900">Duration curve (*_hist)</h2>
      <p className="mt-0.5 text-[11px] text-slate-500">
        Nåværende vs forrige år vs beste i perioden — ikke snapshot-only.
      </p>
      {!data?.curves?.length ? (
        <p className="mt-3 text-xs text-slate-500">Ingen duration-curve historikk.</p>
      ) : (
        <div className="mt-2 overflow-x-auto">
          <table className="w-full min-w-[420px] text-left text-xs">
            <thead>
              <tr className="text-[10px] uppercase tracking-wide text-slate-500">
                <th className="py-1 pr-2">Varighet</th>
                <th className="py-1 pr-2">Nå</th>
                <th className="py-1 pr-2">Forrige år</th>
                <th className="py-1">Beste</th>
              </tr>
            </thead>
            <tbody>
              {data.curves.map((c) => (
                <tr key={c.metric} className="border-t border-slate-100 tabular-nums">
                  <td className="py-1.5 pr-2 font-medium text-slate-800">{c.duration_label}</td>
                  <td className="py-1.5 pr-2">{c.current != null ? c.current.toFixed(2) : "—"}</td>
                  <td className="py-1.5 pr-2">
                    {c.previous_year != null ? c.previous_year.toFixed(2) : "—"}
                  </td>
                  <td className="py-1.5">
                    {c.rolling_best != null ? c.rolling_best.toFixed(2) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data?.disclaimer ? (
        <p className="mt-2 text-[11px] text-slate-500">{data.disclaimer}</p>
      ) : null}
    </section>
  );
}
