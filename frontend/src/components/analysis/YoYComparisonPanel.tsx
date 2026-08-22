"use client";

import type { YoYPayload } from "@/types/analysis";
import { AnalysisSkeleton } from "./ui";

function fmtPct(value?: number | null) {
  if (value == null) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(0)}%`;
}

export function YoYComparisonPanel({ data, isLoading }: { data?: YoYPayload; isLoading?: boolean }) {
  if (isLoading) return <AnalysisSkeleton className="h-40" />;
  const rows = data?.rows?.slice(-6) || [];
  if (!rows.length) {
    return <p className="text-sm text-slate-500">Ingen YoY-data tilgjengelig.</p>;
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-3">
      <h2 className="text-sm font-semibold text-slate-900">År-over-år (volum)</h2>
      <p className="mt-0.5 text-[11px] text-slate-500">
        Sammenligning mot samme måned i fjor — fra månedssammendrag.
      </p>
      <div className="mt-2 overflow-x-auto">
        <table className="min-w-full text-left text-xs">
          <thead className="text-slate-500">
            <tr>
              <th className="py-1.5 pr-3">Måned</th>
              <th className="py-1.5 pr-3">Dist. YoY</th>
              <th className="py-1.5 pr-3">Varighet YoY</th>
              <th className="py-1.5 pr-3">Økter YoY</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.month_label} className="border-t border-slate-100">
                <td className="py-1.5 pr-3 font-medium text-slate-800">{row.month_label}</td>
                <td className="py-1.5 pr-3 tabular-nums">{fmtPct(row.deltas?.distance_pct)}</td>
                <td className="py-1.5 pr-3 tabular-nums">{fmtPct(row.deltas?.duration_pct)}</td>
                <td className="py-1.5 pr-3 tabular-nums">{fmtPct(row.deltas?.activities_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data?.disclaimer ? <p className="mt-2 text-[10px] text-slate-500">{data.disclaimer}</p> : null}
    </section>
  );
}
