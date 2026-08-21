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
    <section aria-labelledby="week-heading" className="rounded-xl border border-border bg-surface px-3 py-2.5">
      <div className="flex flex-wrap items-center justify-between gap-1">
        <h2 id="week-heading" className="text-sm font-semibold text-foreground">
          Denne uken
        </h2>
        {adjusted ? (
          <span className="text-[10px] font-medium text-status-info">Plan justert</span>
        ) : null}
      </div>
      {plan?.week_objective ? (
        <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{plan.week_objective}</p>
      ) : null}
      <ol className="mt-2 grid grid-cols-7 gap-1">
        {DAY_NAMES.map((name, offset) => {
          const s = sessionForDay(sessions, offset);
          const isToday = offset === todayOffset;
          const type = s?.type || "rest";
          return (
            <li
              key={name}
              className={cn(
                "rounded-md border px-0.5 py-1.5 text-center",
                SESSION_CLASS[type] || "bg-surface-muted border-border",
                isToday && "ring-1 ring-foreground/50"
              )}
            >
              <p className="text-[10px] font-medium leading-none text-muted-foreground">
                {name}
                {isToday ? "*" : ""}
              </p>
              <p className="mt-1 text-[10px] font-semibold leading-tight text-foreground sm:text-xs">
                {workoutLabel(type)}
              </p>
              <p className="mt-0.5 text-[9px] leading-tight text-muted-foreground sm:text-[10px]">
                {s?.duration_min != null ? formatDuration(s.duration_min).replace(" min", "m") : "—"}
              </p>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
