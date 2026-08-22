"use client";

import type { PerformanceRecoveryPayload } from "@/types/analysis";
import { AnalysisSkeleton } from "./ui";

export function PerformanceRecoveryHistoryPanel({
  data,
  isLoading,
}: {
  data?: PerformanceRecoveryPayload;
  isLoading?: boolean;
}) {
  if (isLoading) return <AnalysisSkeleton className="h-36" />;
  const rows = data?.months?.slice(-6) || [];
  if (!rows.length) {
    return <p className="text-sm text-slate-500">Ingen månedlig historikk tilgjengelig.</p>;
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-3">
      <h2 className="text-sm font-semibold text-slate-900">Prestasjon og restitusjon</h2>
      <p className="mt-0.5 text-[11px] text-slate-500">
        Månedlige øyeblikksbilder — CTL, HRV og volum.
      </p>
      <div className="mt-2 overflow-x-auto">
        <table className="min-w-full text-left text-xs">
          <thead className="text-slate-500">
            <tr>
              <th className="py-1.5 pr-3">Måned</th>
              <th className="py-1.5 pr-3">Volum (t)</th>
              <th className="py-1.5 pr-3">CTL</th>
              <th className="py-1.5 pr-3">HRV Δ%</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.month} className="border-t border-slate-100">
                <td className="py-1.5 pr-3 font-medium text-slate-800">{row.month}</td>
                <td className="py-1.5 pr-3 tabular-nums">{row.volume_hours ?? "—"}</td>
                <td className="py-1.5 pr-3 tabular-nums">{row.ctl ?? "—"}</td>
                <td className="py-1.5 pr-3 tabular-nums">{row.hrv_delta_pct ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data?.disclaimer ? <p className="mt-2 text-[10px] text-slate-500">{data.disclaimer}</p> : null}
    </section>
  );
}
