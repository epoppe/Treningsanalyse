"use client";

import type { PlannedSession, TodayDashboardPayload } from "@/types/today";
import { workoutTypeLabel } from "./cockpitUtils";
import { cn } from "@/lib/utils";

const WEEKDAY_LABELS = ["Man", "Tir", "Ons", "Tor", "Fre", "Lør", "Søn"];

type WeeklyPlanStripData = {
  as_of?: string;
  weekly_plan?: {
    week_objective?: string;
    sessions?: PlannedSession[];
  };
};

function sessionStatus(session: PlannedSession, dayOffset: number, asOf?: string): "today" | "planned" | "empty" {
  if (!session.type || session.type === "rest") return "empty";
  const todayOffset = getTodayOffset(asOf);
  if (dayOffset === todayOffset) return "today";
  return "planned";
}

function getTodayOffset(asOf?: string): number {
  if (!asOf) return new Date().getDay() === 0 ? 6 : new Date().getDay() - 1;
  const day = new Date(`${asOf}T12:00:00`).getDay();
  return day === 0 ? 6 : day - 1;
}

export function WeeklyPlanStrip({ data }: { data: WeeklyPlanStripData }) {
  const sessions = data.weekly_plan?.sessions || [];

  return (
    <section className="rounded-xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
      <div className="flex items-center justify-between gap-2">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
            Denne uken
          </p>
          <h2 className="mt-1 text-lg font-semibold text-slate-900">Ukeplan</h2>
          {data.weekly_plan?.week_objective ? (
            <p className="text-sm text-slate-600">{data.weekly_plan.week_objective}</p>
          ) : null}
        </div>
      </div>

      <div className="mt-4 grid grid-cols-7 gap-1">
        {WEEKDAY_LABELS.map((label, index) => {
          const session = sessions.find((s) => (s.day_offset ?? -1) === index);
          const status = session
            ? sessionStatus(session, session.day_offset ?? index, data.as_of)
            : "empty";
          return (
            <div
              key={label}
              className={cn(
                "rounded-lg border px-1.5 py-2 text-center",
                status === "today" && "border-slate-900 bg-slate-900 text-white",
                status === "planned" && "border-slate-200 bg-slate-50",
                status === "empty" && "border-dashed border-slate-200 bg-white text-slate-400",
              )}
            >
              <p className="text-[10px] font-semibold">{label}</p>
              <p className="mt-1 text-[10px] leading-tight">
                {session?.type ? workoutTypeLabel(session.type).split(" ")[0] : "—"}
              </p>
            </div>
          );
        })}
      </div>
    </section>
  );
}

export function DevelopmentStrip({ data }: { data: TodayDashboardPayload }) {
  const trends = data.key_trends || [];
  if (!trends.length) return null;

  return (
    <section className="rounded-xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
      <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
        Utvikling
      </p>
      <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {trends.slice(0, 6).map((trend) => (
          <div key={trend.metric} className="rounded-lg border border-slate-100 px-3 py-2">
            <p className="text-sm font-medium text-slate-900">{trend.label || trend.metric}</p>
            <p className="text-xs text-slate-600">
              {trend.relative_change_pct != null
                ? `${trend.relative_change_pct > 0 ? "+" : ""}${trend.relative_change_pct.toFixed(1)}%`
                : trend.direction || "—"}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}
