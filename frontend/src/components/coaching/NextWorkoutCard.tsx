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
      className="relative overflow-hidden rounded-2xl border border-border bg-gradient-to-br from-session-threshold/10 via-surface-elevated to-surface p-6 shadow-sm"
    >
      <div className="absolute inset-x-0 top-0 h-1 bg-session-threshold" aria-hidden />
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Neste økt
      </p>
      <h2 id="next-workout-heading" className="mt-1 text-3xl font-semibold tracking-tight text-foreground">
        {workoutLabel(type)}
      </h2>
      {structure ? <p className="mt-2 text-lg text-foreground/90">{structure}</p> : null}
      <p className="mt-1 text-sm text-muted-foreground">{formatDuration(duration)}</p>

      {!isRest ? (
        <dl className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="rounded-xl bg-surface/80 px-3 py-2">
            <dt className="text-xs text-muted-foreground">Puls</dt>
            <dd className="text-sm font-medium">{formatHrRange(hr)}</dd>
          </div>
          <div className="rounded-xl bg-surface/80 px-3 py-2">
            <dt className="text-xs text-muted-foreground">Tempo</dt>
            <dd className="text-sm font-medium">
              {uncertainPace
                ? "Bruk puls/RPE i dag"
                : Array.isArray(pace)
                  ? `${formatPace(pace[0])}–${formatPace(pace[pace.length - 1])}`
                  : formatPace(pace as number)}
            </dd>
          </div>
        </dl>
      ) : null}

      {uncertainPace && !isRest ? (
        <p className="mt-3 text-sm text-status-warning">
          Tempoestimat usikkert — bruk HR/RPE i dag.
        </p>
      ) : null}

      <div className="mt-4 flex flex-wrap gap-2">
        <StatusBadge status={conf.status} label={conf.label} />
        <StatusBadge status={evidence.status} label={`evidens: ${evidence.label}`} />
        {recommendation?.decision_status ? (
          <StatusBadge status="info" label={String(recommendation.decision_status)} />
        ) : null}
      </div>

      <div className="mt-6 flex flex-wrap gap-3">
        <Link
          href="#why-workout"
          className="rounded-md bg-foreground px-4 py-2 text-sm font-medium text-background"
        >
          Hvorfor denne økten?
        </Link>
        <Link
          href="/plan"
          className="rounded-md border border-border bg-surface px-4 py-2 text-sm font-medium text-foreground"
        >
          Se ukeplan
        </Link>
      </div>
    </section>
  );
}
