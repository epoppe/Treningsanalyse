"use client";

import { cn } from "@/lib/utils";
import type { WeeklyPlan, WeeklyPlanSession } from "@/types/coaching";
import { formatDuration, workoutLabel } from "@/lib/coachingLabels";

const DAY_NAMES = ["Man", "Tir", "Ons", "Tor", "Fre", "Lør", "Søn"];

const SESSION_CLASS: Record<string, string> = {
  easy_run: "bg-session-easy/20 border-session-easy/40",
  recovery_run: "bg-session-easy/20 border-session-easy/40",
  long_run: "bg-session-long/20 border-session-long/40",
  threshold: "bg-session-threshold/20 border-session-threshold/40",
  vo2_intervals: "bg-session-vo2/20 border-session-vo2/40",
  race: "bg-session-race/20 border-session-race/40",
  race_pace: "bg-session-race/20 border-session-race/40",
  strength: "bg-session-strength/20 border-session-strength/40",
  rest: "bg-session-rest/30 border-border",
};

function sessionForDay(sessions: WeeklyPlanSession[], offset: number) {
  return sessions.find((s) => (s.day_offset ?? -1) === offset);
}

export function WeeklyTrainingPlan({
  plan,
  todayOffset = 0,
  adjusted,
}: {
  plan?: WeeklyPlan | null;
  todayOffset?: number;
  adjusted?: boolean;
}) {
  const sessions = plan?.sessions || [];

  return (
    <section aria-labelledby="week-heading" className="rounded-2xl border border-border bg-surface p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="week-heading" className="text-lg font-semibold text-foreground">
          Denne uken
        </h2>
        {adjusted ? (
          <span className="text-xs font-medium text-status-info">Plan justert</span>
        ) : null}
      </div>
      {plan?.week_objective ? (
        <p className="mt-1 text-sm text-muted-foreground">{plan.week_objective}</p>
      ) : null}
      <ol className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
        {DAY_NAMES.map((name, offset) => {
          const s = sessionForDay(sessions, offset);
          const isToday = offset === todayOffset;
          const type = s?.type || "rest";
          return (
            <li
              key={name}
              className={cn(
                "rounded-xl border px-2 py-3 text-center",
                SESSION_CLASS[type] || "bg-surface-muted border-border",
                isToday && "ring-2 ring-foreground/40"
              )}
            >
              <p className="text-xs font-medium text-muted-foreground">
                {name}
                {isToday ? " · i dag" : ""}
              </p>
              <p className="mt-2 text-sm font-semibold text-foreground">
                {workoutLabel(type)}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                {s?.duration_min != null ? formatDuration(s.duration_min) : "—"}
              </p>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
