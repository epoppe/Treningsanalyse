"use client";

import type { PerformanceRecoveryPayload } from "@/types/analysis";
import { AnalysisSkeleton } from "./ui";

const MONTH_OPTIONS = [12, 24, 60];

export function PerformanceRecoveryHistoryPanel({
  data,
  isLoading,
  months = 12,
  onMonthsChange,
}: {
  data?: PerformanceRecoveryPayload;
  isLoading?: boolean;
  months?: number;
  onMonthsChange?: (months: number) => void;
}) {
  if (isLoading) return <AnalysisSkeleton className="h-36" />;
  const rows = data?.months || [];
  if (!rows.length) {
    return <p className="text-sm text-slate-500">Ingen månedlig historikk tilgjengelig.</p>;
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">Prestasjon og restitusjon</h2>
          <p className="mt-0.5 text-[11px] text-slate-500">
            {rows.length} måneder. CTL-slutt er punkt-i-tid. CTL-snitt er gjennomsnitt av daglige tilstander.
          </p>
        </div>
        <div className="flex gap-1">
          {MONTH_OPTIONS.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => onMonthsChange?.(option)}
              className={
                months === option
                  ? "rounded-md bg-slate-900 px-2 py-1 text-[11px] font-medium text-white"
                  : "rounded-md border border-slate-200 px-2 py-1 text-[11px] text-slate-700"
              }
            >
              {option === 60 ? "5å" : `${option}m`}
            </button>
          ))}
        </div>
      </div>
      <div className="mt-2 overflow-x-auto">
        <table className="min-w-full text-left text-xs">
          <thead className="text-slate-500">
            <tr>
              <th className="py-1.5 pr-3">Måned</th>
              <th className="py-1.5 pr-3">Volum (t)</th>
              <th className="py-1.5 pr-3">TSS</th>
              <th className="py-1.5 pr-3">CTL slutt</th>
              <th className="py-1.5 pr-3">CTL snitt</th>
              <th className="py-1.5 pr-3">HRV median</th>
              <th className="py-1.5 pr-3">RHR</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.month} className="border-t border-slate-100">
                <td className="py-1.5 pr-3 font-medium text-slate-800">
                  {row.month}
                  {row.partial ? <span className="ml-1 text-slate-500">MTD</span> : null}
                </td>
                <td className="py-1.5 pr-3 tabular-nums">{row.volume_hours ?? "—"}</td>
                <td className="py-1.5 pr-3 tabular-nums">{row.tss ?? "—"}</td>
                <td className="py-1.5 pr-3 tabular-nums">{row.ctl_end ?? row.ctl ?? "—"}</td>
                <td className="py-1.5 pr-3 tabular-nums">{row.ctl_mean ?? "—"}</td>
                <td className="py-1.5 pr-3 tabular-nums">{row.hrv_median ?? "—"}</td>
                <td className="py-1.5 pr-3 tabular-nums">{row.rhr_median ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data?.disclaimer ? <p className="mt-2 text-[10px] text-slate-500">{data.disclaimer}</p> : null}
    </section>
  );
}
