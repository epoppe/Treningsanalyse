"use client";

import Link from "next/link";
import type { PlanVsActualDay } from "@/types/plan";
import { workoutTypeLabel } from "./cockpitUtils";

const WEEKDAY_LABELS = ["Man", "Tir", "Ons", "Tor", "Fre", "Lør", "Søn"];

function statusLabel(status?: string): string {
  const labels: Record<string, string> = {
    followed: "Fulgt",
    modified: "Justert",
    missed: "Ikke gjennomført",
    unplanned: "Uplanlagt aktivitet",
    rest: "Hvile",
    replaced: "Erstattet",
    completed: "Fullført",
    partial: "Delvis",
  };
  if (!status) return "—";
  return labels[status] || status.replace(/_/g, " ");
}

function statusTone(status?: string): string {
  if (status === "followed" || status === "completed") return "text-emerald-700";
  if (status === "modified" || status === "partial") return "text-amber-700";
  if (status === "missed") return "text-rose-700";
  return "text-slate-600";
}

export function PlanVsActualTable({ days }: { days?: PlanVsActualDay[] }) {
  const rows = days || [];
  if (!rows.length) {
    return <p className="text-sm text-slate-600">Ingen plan vs. faktisk-data for denne uken.</p>;
  }

  return (
    <div className="mt-3 overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead className="text-xs uppercase text-slate-500">
          <tr>
            <th className="py-2 pr-4">Dag</th>
            <th className="py-2 pr-4">Planlagt</th>
            <th className="py-2 pr-4">Faktisk</th>
            <th className="py-2 pr-4">Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const weekday =
              row.weekday != null ? WEEKDAY_LABELS[row.weekday] : row.date?.slice(5);
            return (
              <tr key={row.date || row.day_offset} className="border-t border-slate-100">
                <td className="py-2 pr-4 tabular-nums text-slate-700">{weekday}</td>
                <td className="py-2 pr-4">
                  {row.planned_type && row.planned_type !== "rest"
                    ? workoutTypeLabel(row.planned_type)
                    : "Hvile"}
                </td>
                <td className="py-2 pr-4">
                  {row.actual_type ? (
                    row.activity_id ? (
                      <Link
                        href={`/activities/${row.activity_id}`}
                        className="underline decoration-slate-300 underline-offset-2 hover:text-slate-900"
                      >
                        {workoutTypeLabel(row.actual_type)}
                      </Link>
                    ) : (
                      workoutTypeLabel(row.actual_type)
                    )
                  ) : (
                    "—"
                  )}
                </td>
                <td className={`py-2 pr-4 ${statusTone(row.execution_status)}`}>
                  {statusLabel(row.execution_status)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
