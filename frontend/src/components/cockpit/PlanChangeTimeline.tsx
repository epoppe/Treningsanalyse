"use client";

import type { PlanVersionEntry } from "@/types/plan";
import { planReasonLabel, workoutTypeLabel } from "./cockpitUtils";

function formatChange(change: Record<string, unknown>): string {
  const fromType = change.from ?? change.from_type;
  const toType = change.to ?? change.to_type;
  if (fromType && toType) {
    return `${workoutTypeLabel(String(fromType))} → ${workoutTypeLabel(String(toType))}`;
  }
  if (change.action === "delay_quality" && change.hours) {
    return `Kvalitetsøkt utsatt ${change.hours} timer`;
  }
  return "Planjustering";
}

export function PlanChangeTimeline({ history }: { history?: PlanVersionEntry[] }) {
  const entries = history || [];
  if (!entries.length) {
    return (
      <p className="text-sm text-slate-600">
        Ingen registrerte planendringer ennå — planen følger siste vurdering.
      </p>
    );
  }

  return (
    <ol className="mt-3 space-y-3">
      {entries.map((entry) => {
        const reasons = (entry.reason || []).map((r) => planReasonLabel(String(r)));
        const changes = (entry.changes || []).map(formatChange);
        return (
          <li
            key={`${entry.version}-${entry.created_at}`}
            className="rounded-lg border border-slate-100 px-3 py-2"
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                {entry.week_objective ? (
                  <p className="text-sm font-medium text-slate-900">{entry.week_objective}</p>
                ) : null}
                {reasons.length ? (
                  <ul className="mt-1 list-inside list-disc text-xs text-slate-600">
                    {reasons.map((reason) => (
                      <li key={reason}>{reason}</li>
                    ))}
                  </ul>
                ) : null}
                {changes.length ? (
                  <p className="mt-1 text-xs text-slate-500">{changes.join(" · ")}</p>
                ) : null}
              </div>
              {entry.created_at ? (
                <time className="shrink-0 text-[10px] text-slate-400 tabular-nums">
                  {new Intl.DateTimeFormat("nb-NO", {
                    day: "numeric",
                    month: "short",
                  }).format(new Date(entry.created_at))}
                </time>
              ) : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
