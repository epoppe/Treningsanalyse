"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { AnalysisSkeleton } from "@/components/analysis/ui";
import { workoutTypeLabel } from "@/components/cockpit/cockpitUtils";
import { useRecommendationHistory } from "@/hooks/useDashboard";
import type { RecommendationHistoryItem } from "@/types/dashboard";

type ExecutionFilter = "all" | "followed" | "modified" | "skipped";

const FILTERS: Array<{ id: ExecutionFilter; label: string }> = [
  { id: "all", label: "Alle" },
  { id: "followed", label: "Fulgt" },
  { id: "modified", label: "Justert" },
  { id: "skipped", label: "Hoppet over" },
];

function executionLabel(status?: string | null) {
  if (status === "followed") return "Fulgt";
  if (status === "modified") return "Justert";
  if (status === "skipped" || status === "missed") return "Hoppet over";
  return status || "—";
}

function executionTone(status?: string | null) {
  if (status === "followed") return "text-emerald-700";
  if (status === "modified") return "text-amber-700";
  if (status === "skipped" || status === "missed") return "text-slate-500";
  return "text-slate-600";
}

function qualityLabel(item: RecommendationHistoryItem) {
  if (item.execution_quality == null) return "—";
  return `${Math.round(item.execution_quality * 100)}%`;
}

export function RecommendationHistoryPanel() {
  const [filter, setFilter] = useState<ExecutionFilter>("all");
  const history = useRecommendationHistory(40, filter === "all" ? undefined : filter);

  const items = useMemo(() => history.data?.items || [], [history.data]);

  return (
    <section className="rounded-xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
      <h2 className="text-sm font-semibold text-slate-900">Anbefalingshistorikk</h2>
      <p className="mt-1 text-xs text-slate-500">
        Ledger + gjennomføring — observasjonelt, ikke moraliserende. Brukes til å vurdere coaching
        over tid.
      </p>

      <div className="mt-3 flex flex-wrap gap-1">
        {FILTERS.map((opt) => (
          <button
            key={opt.id}
            type="button"
            onClick={() => setFilter(opt.id)}
            className={
              filter === opt.id
                ? "rounded-md bg-slate-900 px-2 py-1 text-[11px] font-medium text-white"
                : "rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-[11px] text-slate-700"
            }
          >
            {opt.label}
          </button>
        ))}
      </div>

      {history.isLoading ? <AnalysisSkeleton className="mt-3 h-24" /> : null}

      {items.length ? (
        <div className="mt-3 overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="text-xs uppercase text-slate-500">
              <tr>
                <th className="py-2 pr-4">Dato</th>
                <th className="py-2 pr-4">Anbefalt</th>
                <th className="py-2 pr-4">Faktisk</th>
                <th className="py-2 pr-4">Gjennomføring</th>
                <th className="py-2 pr-4">Kvalitet</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id} className="border-t border-slate-100">
                  <td className="py-2 pr-4 tabular-nums">{item.as_of_date}</td>
                  <td className="py-2 pr-4">{workoutTypeLabel(item.recommended)}</td>
                  <td className="py-2 pr-4">
                    {item.activity_id ? (
                      <Link
                        href={`/activities/${item.activity_id}`}
                        className="underline decoration-slate-300 underline-offset-2"
                      >
                        {workoutTypeLabel(item.actual_type) || "Økt"}
                      </Link>
                    ) : item.actual_type ? (
                      workoutTypeLabel(item.actual_type)
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className={`py-2 pr-4 ${executionTone(item.execution_status)}`}>
                    {executionLabel(item.execution_status)}
                  </td>
                  <td className="py-2 pr-4 tabular-nums text-slate-600">
                    {qualityLabel(item)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : !history.isLoading ? (
        <p className="mt-3 text-sm text-slate-600">
          Ingen lagrede anbefalinger{filter !== "all" ? ` for «${executionLabel(filter)}»` : ""} ennå.
        </p>
      ) : null}

      {history.data?.disclaimer ? (
        <p className="mt-2 text-[10px] text-slate-500">{history.data.disclaimer}</p>
      ) : null}
    </section>
  );
}
