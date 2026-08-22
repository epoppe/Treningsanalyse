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
}: {
  data?: WeekExplorerPayload;
  isLoading?: boolean;
  onPreviousWeek?: (weekStart: string) => void;
}) {
  if (isLoading) return <AnalysisSkeleton className="h-40" />;
  if (!data) return null;

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">Ukeutforsker</h2>
          <p className="text-xs text-slate-500">
            {data.week_start} – {data.week_end}
          </p>
        </div>
        {data.compare_links?.previous_week && onPreviousWeek ? (
          <button
            type="button"
            onClick={() => onPreviousWeek(data.compare_links!.previous_week!)}
            className="text-xs font-medium text-slate-700 underline"
          >
            Forrige uke
          </button>
        ) : null}
      </div>

      {data.summary ? (
        <p className="mt-2 text-xs text-slate-600">
          {data.summary.activity_count ?? data.sessions.length} økter ·{" "}
          {fmtKm(data.summary.total_distance)} ·{" "}
          {data.summary.total_duration != null
            ? fmtMin(data.summary.total_duration)
            : "—"}
        </p>
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
