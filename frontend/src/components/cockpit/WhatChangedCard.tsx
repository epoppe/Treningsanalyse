"use client";

import type { WhatChangedPayload } from "@/types/dashboard";
import { workoutTypeLabel } from "./cockpitUtils";

function directionArrow(direction?: string) {
  const d = (direction || "").toLowerCase();
  if (d === "improved") return "↑";
  if (d === "worsened") return "↓";
  if (d === "changed") return "↔";
  return "→";
}

export function WhatChangedCard({ data }: { data: WhatChangedPayload }) {
  const changes = data.material_changes || [];

  return (
    <section className="rounded-xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
      <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
        Hva endret seg
      </p>
      <p className="mt-1 text-sm text-slate-700">{data.summary}</p>

      {data.recommendation_changed ? (
        <p className="mt-2 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-800">
          Anbefaling:{" "}
          <span className="font-medium">
            {workoutTypeLabel(data.before_recommendation)} →{" "}
            {workoutTypeLabel(data.after_recommendation)}
          </span>
        </p>
      ) : null}

      {changes.length > 0 ? (
        <ul className="mt-3 space-y-2">
          {changes.slice(0, 6).map((change) => (
            <li
              key={change.metric}
              className="flex items-center justify-between gap-3 rounded-lg border border-slate-100 px-3 py-2 text-sm"
            >
              <span className="font-medium text-slate-800">{change.label}</span>
              <span className="tabular-nums text-slate-600">
                {directionArrow(change.direction)} {String(change.before)} → {String(change.after)}
              </span>
            </li>
          ))}
        </ul>
      ) : !data.recommendation_changed ? (
        <p className="mt-2 text-xs text-slate-500">
          Ingen materielle signalendringer siden forrige oppdatering.
        </p>
      ) : null}
    </section>
  );
}
