"use client";

import type { PeriodComparisonRow } from "@/types/analysis";
import { PeriodExplanationPanel } from "./PeriodExplanationPanel";
import { EvidenceBadge } from "./ui";

export function PeriodComparison({
  rows,
  disclaimer,
}: {
  rows: PeriodComparisonRow[];
  disclaimer?: string;
}) {
  const notable = rows.filter((r) => r.difference != null).slice(0, 10);
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="text-sm font-semibold text-slate-900">Periode-sammenligning</h2>
      <p className="mt-0.5 text-[11px] text-slate-500">Siste vindu vs forrige like lange vindu</p>
      <PeriodExplanationPanel rows={rows} />
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[480px] text-left text-xs">
          <thead className="border-b border-slate-200 text-slate-500">
            <tr>
              <th className="py-1.5 font-medium">Metrikk</th>
              <th className="py-1.5 font-medium">A</th>
              <th className="py-1.5 font-medium">B</th>
              <th className="py-1.5 font-medium">Δ</th>
              <th className="py-1.5 font-medium">Evidens</th>
            </tr>
          </thead>
          <tbody>
            {notable.map((r) => (
              <tr key={r.metric} className="border-b border-slate-100">
                <td className="py-1.5 font-medium text-slate-800">{r.metric}</td>
                <td className="py-1.5 tabular-nums">
                  {r.period_a.value == null ? "—" : Number(r.period_a.value).toFixed(1)}
                </td>
                <td className="py-1.5 tabular-nums">
                  {r.period_b.value == null ? "—" : Number(r.period_b.value).toFixed(1)}
                </td>
                <td className="py-1.5 tabular-nums">
                  {r.difference == null
                    ? "—"
                    : `${r.difference > 0 ? "+" : ""}${Number(r.difference).toFixed(1)}`}
                </td>
                <td className="py-1.5">
                  <EvidenceBadge evidence={r.evidence} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {disclaimer ? <p className="mt-2 text-[11px] text-slate-500">{disclaimer}</p> : null}
    </section>
  );
}
