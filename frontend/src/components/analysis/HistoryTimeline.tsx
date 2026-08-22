"use client";

import Link from "next/link";
import type { HistoryPayload } from "@/types/analysis";

function fmtKm(meters?: number | null) {
  if (meters == null) return "—";
  return `${(meters / 1000).toFixed(0)} km`;
}

function fmtHours(seconds?: number | null) {
  if (seconds == null) return "—";
  return `${(seconds / 3600).toFixed(1)} t`;
}

export function HistoryTimeline({ data }: { data: HistoryPayload }) {
  return (
    <section className="space-y-3">
      {data.years.length === 0 ? (
        <p className="text-sm text-slate-500">Ingen månedssammendrag i perioden.</p>
      ) : (
        data.years.map((year) => (
          <details key={year.year} open className="rounded-lg border border-slate-200 bg-white">
            <summary className="cursor-pointer px-3 py-2 text-sm font-semibold text-slate-900">
              {year.year}
              <span className="ml-2 text-xs font-normal text-slate-500">
                {year.months.length} måneder
              </span>
            </summary>
            <ul className="border-t border-slate-100 px-2 py-2">
              {year.months.map((m) => {
                const key = m.month_start || `${m.year}-${m.month}`;
                const weekHref = m.month_start
                  ? `/analyse?tab=historikk&week=${m.month_start}`
                  : undefined;
                return (
                  <li
                    key={key}
                    className="flex flex-wrap items-center justify-between gap-2 rounded-md px-2 py-1.5 text-xs hover:bg-slate-50"
                  >
                    <div>
                      <p className="font-medium text-slate-800">
                        {m.month_start || `${m.year}-${m.month}`}
                      </p>
                      <p className="text-slate-500">
                        {m.activity_count ?? 0} økter · {fmtKm(m.total_distance_meters)} ·{" "}
                        {fmtHours(m.total_duration_seconds)}
                      </p>
                    </div>
                    {weekHref ? (
                      <Link href={weekHref} className="text-[11px] text-sky-700 underline">
                        Utforsk uke
                      </Link>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          </details>
        ))
      )}
      {data.note ? <p className="text-[11px] text-slate-500">{data.note}</p> : null}
    </section>
  );
}
