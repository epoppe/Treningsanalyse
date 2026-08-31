"use client";

import Link from "next/link";
import type { WeekExplorerPayload } from "@/types/analysis";
import { AnalysisSkeleton } from "./ui";

function fmtKm(meters?: number | null) {
  if (meters == null) return "—";
  return `${(meters / 1000).toFixed(1)} km`;
}

function fmtMin(seconds?: number | null) {
  if (seconds == null) return "—";
  return `${Math.round(seconds / 60)} min`;
}

export function WeekExplorer({
  data,
  isLoading,
  onPreviousWeek,
  onFollowingRange,
}: {
  data?: WeekExplorerPayload;
  isLoading?: boolean;
  onPreviousWeek?: (weekStart: string) => void;
  onFollowingRange?: (from: string, to: string) => void;
}) {
  if (isLoading) return <AnalysisSkeleton className="h-40" />;
  if (!data) return null;

  const links = data.compare_links || {};
  const similarWeek = (() => {
    const start = new Date(`${data.week_start}T12:00:00Z`);
    start.setUTCFullYear(start.getUTCFullYear() - 1);
    return start.toISOString().slice(0, 10);
  })();

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">Ukeutforsker</h2>
          <p className="text-xs text-slate-500">
            {data.week_start} – {data.week_end}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {links.previous_week && onPreviousWeek ? (
            <button
              type="button"
              onClick={() => onPreviousWeek(links.previous_week!)}
              className="text-xs font-medium text-slate-700 underline"
            >
              COMPARE PREVIOUS WEEK
            </button>
          ) : null}
          {onPreviousWeek ? (
            <button
              type="button"
              onClick={() => onPreviousWeek(similarWeek)}
              className="text-xs font-medium text-slate-700 underline"
            >
              COMPARE SIMILAR WEEK
            </button>
          ) : null}
          {links.following_4_weeks_start &&
          links.following_4_weeks_end &&
          onFollowingRange ? (
            <button
              type="button"
              onClick={() =>
                onFollowingRange(links.following_4_weeks_start!, links.following_4_weeks_end!)
              }
              className="text-xs font-medium text-slate-700 underline"
            >
              SHOW FOLLOWING 4 WEEKS
            </button>
          ) : null}
        </div>
      </div>

      {data.summary ? (
        <div className="mt-3 grid gap-2 sm:grid-cols-3">
          <div className="rounded-md border border-slate-100 bg-slate-50 px-2 py-1.5 text-xs">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
              Training
            </p>
            <p className="mt-1 text-slate-800">
              {data.summary.activity_count ?? data.sessions.length} økter ·{" "}
              {fmtKm(data.summary.total_distance)} ·{" "}
              {data.summary.total_duration != null
                ? fmtMin(data.summary.total_duration)
                : "—"}
            </p>
          </div>
          <div className="rounded-md border border-slate-100 bg-slate-50 px-2 py-1.5 text-xs">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
              State
            </p>
            <p className="mt-1 text-slate-800">CTL/ATL/TSB: se belastningsgraf</p>
          </div>
          <div className="rounded-md border border-slate-100 bg-slate-50 px-2 py-1.5 text-xs">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
              Recovery / outcome
            </p>
            <p className="mt-1 text-slate-800">
              Snittpuls {data.summary.avg_heart_rate != null ? Math.round(data.summary.avg_heart_rate) : "—"} · EF i utvikling
            </p>
          </div>
        </div>
      ) : null}

      <ul className="mt-3 space-y-1">
        {data.sessions.length ? (
          data.sessions.map((session) => (
            <li
              key={session.activity_id || `${session.date}-${session.name}`}
              className="flex items-center justify-between gap-2 rounded-md border border-slate-100 px-2 py-1.5 text-xs"
            >
              <div>
                <p className="font-medium text-slate-800">{session.name || "Økt"}</p>
                <p className="text-slate-500">
                  {session.date} · {session.type || "—"} · {fmtKm(session.distance_m)} ·{" "}
                  {fmtMin(session.duration_s)}
                </p>
              </div>
              {session.activity_id ? (
                <Link
                  href={`/activities/${session.activity_id}`}
                  className="shrink-0 font-medium text-slate-900 underline"
                >
                  Detalj
                </Link>
              ) : null}
            </li>
          ))
        ) : (
          <li className="text-sm text-slate-500">Ingen registrerte økter denne uken.</li>
        )}
      </ul>
    </section>
  );
}
