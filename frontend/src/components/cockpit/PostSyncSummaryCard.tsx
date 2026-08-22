"use client";

import Link from "next/link";
import type { PostSyncSummaryPayload } from "@/types/dashboard";
import { workoutTypeLabel } from "./cockpitUtils";

const QUALITY_LABELS: Record<string, string> = {
  good: "God",
  moderate: "Middels",
  weak: "Svak",
  unknown: "Ukjent",
};

const COMPARISON_LABELS: Record<string, string> = {
  above_average: "Over gjennomsnittet",
  below_average: "Under gjennomsnittet",
  typical: "Typisk",
};

export function PostSyncSummaryCard({ data }: { data: PostSyncSummaryPayload }) {
  const quality = data.session_quality;
  const comparable = data.comparable;

  return (
    <section className="rounded-xl border border-sky-200 bg-sky-50 px-4 py-4 shadow-sm">
      <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-sky-700">
        Ny økt analysert
      </p>
      <h2 className="mt-1 text-lg font-semibold text-slate-900">
        {data.activity_name || "Siste økt"}
      </h2>
      <p className="text-sm text-slate-600">
        {workoutTypeLabel(data.session_type)} · Kvalitet:{" "}
        {QUALITY_LABELS[quality?.label || "unknown"]}
        {quality?.score != null ? ` (${quality.score})` : ""}
      </p>

      {comparable?.count ? (
        <p className="mt-2 text-sm text-slate-700">
          Sammenlignet med {comparable.count} lignende økter:{" "}
          {COMPARISON_LABELS[comparable.comparison_label || ""] ||
            (comparable.percentile != null ? `topp ${Math.round(100 - comparable.percentile)}%` : "—")}
        </p>
      ) : (
        <p className="mt-2 text-sm text-slate-600">For få sammenlignbare økter ennå.</p>
      )}

      {data.interpretation ? (
        <p className="mt-2 text-xs text-slate-600">{data.interpretation}</p>
      ) : null}

      {data.activity_id ? (
        <Link
          href={`/activities/${data.activity_id}`}
          className="mt-3 inline-block text-sm font-medium text-sky-800 underline"
        >
          Åpne øktdetaljer
        </Link>
      ) : null}
    </section>
  );
}
