"use client";

import Link from "next/link";
import type { TodayDashboardPayload } from "@/types/today";
import { EvidenceBadge } from "@/components/analysis/ui";
import {
  evidenceBand,
  formatHrRange,
  formatPaceRange,
  formatRpeRange,
  mainSetSummary,
  workoutTypeLabel,
} from "./cockpitUtils";
import { cn } from "@/lib/utils";

function TargetRow({ label, value }: { label: string; value: string | null }) {
  if (!value) return null;
  return (
    <div className="flex items-center justify-between gap-3 text-sm">
      <span className="text-slate-500">{label}</span>
      <span className="font-medium tabular-nums text-slate-900">{value}</span>
    </div>
  );
}

function AlternativeCard({ option, index }: { option: Record<string, unknown>; index: number }) {
  const type = String(option.workout_type || option.type || "easy_run");
  const prescription = (option.prescription || option.workout_prescription) as
    | Record<string, unknown>
    | undefined;
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
        Alternativ {String.fromCharCode(65 + index)}
      </p>
      <p className="mt-1 text-sm font-semibold text-slate-900">{workoutTypeLabel(type)}</p>
      {prescription?.total_duration_min ? (
        <p className="text-xs text-slate-600">~{String(prescription.total_duration_min)} min</p>
      ) : null}
      {option.rationale ? (
        <p className="mt-1 text-xs text-slate-600">{String(option.rationale)}</p>
      ) : null}
    </div>
  );
}

export function NextWorkoutCard({ data }: { data: TodayDashboardPayload }) {
  const rec = data.recommendation;
  const status = rec?.decision_status;
  const prescription = rec?.prescription;
  const workoutType = rec?.workout_type || rec?.workout?.type;
  const title = prescription?.title || workoutTypeLabel(workoutType);
  const mainSummary = mainSetSummary(prescription);
  const hr =
    formatHrRange(prescription?.target_hr || prescription?.main_set?.target_hr || rec?.workout?.target_hr) ||
    null;
  const pace =
    formatPaceRange(
      prescription?.target_pace || prescription?.main_set?.target_pace || rec?.workout?.target_pace,
    ) || null;
  const rpe = formatRpeRange(prescription?.target_rpe || prescription?.main_set?.target_rpe) || null;
  const isAbstain = status === "abstain" || status === "insufficient_data";
  const alternatives = (rec?.safe_alternatives || data.decision_explanation?.alternatives || []).slice(0, 2);

  return (
    <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-100 bg-slate-900 px-4 py-3 text-white">
        <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-300">
          Neste økt
        </p>
        {!isAbstain ? (
          <>
            <h2 className="mt-1 text-xl font-semibold tracking-tight">{title}</h2>
            {mainSummary ? (
              <pre className="mt-2 whitespace-pre-wrap font-sans text-sm text-slate-200">{mainSummary}</pre>
            ) : null}
            {prescription?.total_duration_min ? (
              <p className="mt-2 text-sm text-slate-300">
                Total ~{prescription.total_duration_min} min
              </p>
            ) : rec?.workout?.duration_min ? (
              <p className="mt-2 text-sm text-slate-300">Total ~{rec.workout.duration_min} min</p>
            ) : null}
          </>
        ) : (
          <>
            <h2 className="mt-1 text-xl font-semibold tracking-tight">To trygge alternativer</h2>
            <p className="mt-1 text-sm text-slate-300">
              Evidensten er for svak til én entydig anbefaling — velg det tryggeste alternativet.
            </p>
          </>
        )}
      </div>

      <div className="space-y-3 px-4 py-4">
        {!isAbstain ? (
          <>
            <div className="space-y-1.5">
              <TargetRow label="Puls" value={hr} />
              <TargetRow label="Tempo" value={pace} />
              <TargetRow label="Anstrengelse" value={rpe} />
            </div>
            {prescription?.pace_certainty === "low" || !pace ? (
              <p className="rounded-md bg-amber-50 px-2.5 py-2 text-xs text-amber-900">
                Bruk puls/RPE — tempomål er mindre sikkert.
              </p>
            ) : null}
            {prescription?.intensity_source ? (
              <p className="text-xs text-slate-500">
                Intensitet basert på {prescription.intensity_source}.
              </p>
            ) : null}
            <div className="flex items-center gap-2">
              <EvidenceBadge evidence={evidenceBand(rec?.evidence_strength)} />
              <span className="text-[11px] text-slate-500">
                Konfidens {rec?.confidence != null ? `${Math.round(rec.confidence * 100)}%` : "—"}
              </span>
            </div>
          </>
        ) : (
          <div className="grid gap-2 sm:grid-cols-2">
            {alternatives.length > 0 ? (
              alternatives.map((option, index) => (
                <AlternativeCard key={index} option={option as Record<string, unknown>} index={index} />
              ))
            ) : (
              <p className="text-sm text-slate-600">
                Ingen trygge alternativer returnert — velg rolig økt eller hvile.
              </p>
            )}
          </div>
        )}

        <Link
          href="/plan"
          className={cn(
            "inline-flex w-full items-center justify-center rounded-lg bg-slate-900 px-4 py-2.5",
            "text-sm font-medium text-white transition hover:bg-slate-800",
          )}
        >
          Se ukeplan
        </Link>
      </div>
    </section>
  );
}
