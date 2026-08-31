"use client";

import type { TrainingResponsePayload } from "@/types/analysis";
import { EvidenceBadge } from "./ui";

const OUTCOME_OPTIONS = [
  { key: "fitness.ef_30d", label: "Aerob effektivitet" },
  { key: "running.critical_speed", label: "Critical speed" },
  { key: "running.durability_score", label: "Durability" },
  { key: "cardio.hrv_7d", label: "HRV / restitusjon" },
];

export function TrainingResponsePanel({
  outcome,
  onOutcomeChange,
  data,
  isLoading,
}: {
  outcome: string;
  onOutcomeChange: (key: string) => void;
  data?: TrainingResponsePayload;
  isLoading?: boolean;
}) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="text-sm font-semibold text-slate-900">Trening → respons</h2>
      <p className="mt-0.5 text-[11px] text-slate-500">
        Velg utfall — systemet foreslår historisk støttede stimuli (observasjonelt).
      </p>
      <div className="mt-2 flex flex-wrap gap-1">
        {OUTCOME_OPTIONS.map((o) => (
          <button
            key={o.key}
            type="button"
            onClick={() => onOutcomeChange(o.key)}
            className={
              outcome === o.key
                ? "rounded-md bg-slate-900 px-2 py-1 text-[11px] font-medium text-white"
                : "rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-[11px] text-slate-700"
            }
          >
            {o.label}
          </button>
        ))}
      </div>
      {isLoading ? <p className="mt-3 text-xs text-slate-500">Laster…</p> : null}
      {data?.suggested_predictors?.length ? (
        <p className="mt-2 text-[11px] text-slate-600">
          Foreslåtte prediktorer: {data.suggested_predictors.join(", ")}
        </p>
      ) : null}
      <ul className="mt-2 space-y-1.5">
        {(data?.relationships || []).slice(0, 8).map((r, i) => (
          <li
            key={`${r.stimulus}-${r.outcome}-${i}`}
            className="rounded-md border border-slate-100 px-2 py-1.5 text-xs text-slate-700"
          >
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="font-medium">
                {(r.stimulus || "?").replace(/_/g, " ")} → {(r.outcome || "?").replace(/_/g, " ")}
              </span>
              <span className="rounded bg-slate-100 px-1 text-[10px]">{r.association}</span>
              {r.evidence ? <EvidenceBadge evidence={String(r.evidence)} /> : null}
              {r.lag_days != null ? (
                <span className="text-[10px] text-slate-500">lag {r.lag_days}d</span>
              ) : null}
              <span className="text-[10px] text-slate-500">n={r.sample_count ?? 0}</span>
            </div>
            {r.wording ? <p className="mt-1 text-[11px] text-slate-500">{r.wording}</p> : null}
          </li>
        ))}
      </ul>
      {!isLoading && !(data?.relationships || []).length ? (
        <p className="mt-2 text-xs text-slate-500">Ingen støttede sammenhenger for valgt utfall.</p>
      ) : null}
      {data?.disclaimer ? (
        <p className="mt-2 text-[11px] text-slate-500">{data.disclaimer}</p>
      ) : null}
    </section>
  );
}
