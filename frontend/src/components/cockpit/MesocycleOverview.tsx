"use client";

import type { MesocycleWeek } from "@/types/plan";
import { phaseLabel, workoutTypeLabel } from "./cockpitUtils";

function formatVolume(target?: number[]): string {
  if (!target || target.length < 2) return "—";
  return `${target[0]}–${target[1]} min`;
}

export function MesocycleOverview({ weeks }: { weeks?: MesocycleWeek[] }) {
  const rows = weeks || [];
  if (!rows.length) {
    return <p className="text-sm text-slate-600">Mesosyklus ikke tilgjengelig.</p>;
  }

  return (
    <div className="mt-3 space-y-2">
      {rows.map((week) => (
        <div
          key={week.week || week.week_index}
          className="rounded-lg border border-slate-100 px-3 py-3"
        >
          <div className="flex items-center justify-between gap-2">
            <p className="text-sm font-medium text-slate-900">Uke {week.week || week.week_index}</p>
            {week.phase ? (
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-600">
                {phaseLabel(week.phase)}
              </span>
            ) : null}
          </div>
          <div className="mt-2 grid gap-1 text-xs text-slate-600 sm:grid-cols-2">
            <p>Volum: {formatVolume(week.target_volume)}</p>
            <p>Kvalitetsøkter: {week.quality_sessions ?? "—"}</p>
            {week.primary_stimulus ? (
              <p>Primær: {workoutTypeLabel(week.primary_stimulus)}</p>
            ) : null}
            {week.secondary_stimulus ? (
              <p>Sekundær: {workoutTypeLabel(week.secondary_stimulus)}</p>
            ) : null}
            {week.deload_state === "recommended" ? (
              <p className="text-amber-700">Avlastning anbefalt</p>
            ) : null}
          </div>
        </div>
      ))}
    </div>
  );
}
