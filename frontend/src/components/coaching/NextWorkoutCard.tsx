"use client";

import Link from "next/link";
import type { NextWorkout, WorkoutPrescription } from "@/types/coaching";
import {
  formatDuration,
  formatHrRange,
  formatPace,
  workoutLabel,
} from "@/lib/coachingLabels";
import { StatusBadge } from "./ui-states";

function confidenceLabel(n?: number | null): { status: "positive" | "warning" | "muted"; label: string } {
  if (n == null) return { status: "muted", label: "usikker" };
  if (n >= 0.7) return { status: "positive", label: "høy tillit" };
  if (n >= 0.45) return { status: "warning", label: "moderat tillit" };
  return { status: "muted", label: "lav tillit" };
}

export function NextWorkoutCard({
  recommendation,
  prescription,
}: {
  recommendation?: NextWorkout | null;
  prescription?: WorkoutPrescription | null;
}) {
  const type = recommendation?.workout_type;
  const main = prescription?.main_set;
  const conf = confidenceLabel(recommendation?.decision_confidence);
  const evidence = confidenceLabel(recommendation?.evidence_strength);
  const hr = recommendation?.target_hr || (main?.target_hr as number[] | undefined);
  const pace = recommendation?.target_pace || (main?.target_pace_sec_km as number[] | undefined);
  const duration =
    recommendation?.duration_min ??
    prescription?.total_duration_min ??
    null;

  const structure =
    main?.repetitions && main?.work_duration_min
      ? `${main.repetitions} × ${main.work_duration_min} min`
      : null;

  const isRest = type === "rest";
  const uncertainPace = !pace || (Array.isArray(pace) && pace.length === 0);

  return (
    <section
      aria-labelledby="next-workout-heading"
      className="relative overflow-hidden rounded-xl border border-border bg-gradient-to-br from-session-threshold/10 via-surface-elevated to-surface px-3 py-3"
    >
      <div className="absolute inset-x-0 top-0 h-0.5 bg-session-threshold" aria-hidden />
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
            Neste økt
          </p>
          <h2 id="next-workout-heading" className="text-xl font-semibold tracking-tight text-foreground">
            {workoutLabel(type)}
          </h2>
          <p className="mt-0.5 text-sm text-foreground/90">
            {[structure, formatDuration(duration)].filter(Boolean).join(" · ")}
          </p>
        </div>
        <div className="flex flex-wrap justify-end gap-1">
          <StatusBadge status={conf.status} label={conf.label} />
          <StatusBadge status={evidence.status} label={`evidens: ${evidence.label}`} />
        </div>
      </div>

      {!isRest ? (
        <dl className="mt-2.5 grid grid-cols-2 gap-1.5">
          <div className="rounded-lg bg-surface/80 px-2 py-1.5">
            <dt className="text-[10px] text-muted-foreground">Puls</dt>
            <dd className="text-sm font-medium tabular-nums">{formatHrRange(hr)}</dd>
          </div>
          <div className="rounded-lg bg-surface/80 px-2 py-1.5">
            <dt className="text-[10px] text-muted-foreground">Tempo</dt>
            <dd className="text-sm font-medium">
              {uncertainPace
                ? "HR/RPE i dag"
                : Array.isArray(pace)
                  ? `${formatPace(pace[0])}–${formatPace(pace[pace.length - 1])}`
                  : formatPace(pace as number)}
            </dd>
          </div>
        </dl>
      ) : null}

      {uncertainPace && !isRest ? (
        <p className="mt-1.5 text-xs text-status-warning">Tempoestimat usikkert — bruk HR/RPE.</p>
      ) : null}

      <div className="mt-2.5 flex flex-wrap gap-2">
        <Link
          href="#why-workout"
          className="rounded-md bg-foreground px-3 py-1.5 text-xs font-medium text-background"
        >
          Hvorfor?
        </Link>
        <Link
          href="/plan"
          className="rounded-md border border-border bg-surface px-3 py-1.5 text-xs font-medium text-foreground"
        >
          Ukeplan
        </Link>
      </div>
    </section>
  );
}
