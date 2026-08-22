"use client";

import { useState } from "react";
import Link from "next/link";
import type { PostSyncSummaryPayload, WhatChangedPayload } from "@/types/dashboard";
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

export function SinceLastUpdate({
  whatChanged,
  postSync,
}: {
  whatChanged?: WhatChangedPayload | null;
  postSync?: PostSyncSummaryPayload | null;
}) {
  const [expanded, setExpanded] = useState(false);
  if (!whatChanged && !postSync) return null;

  const recChanged = Boolean(whatChanged?.recommendation_changed);
  const headline = postSync
    ? recChanged
      ? `Ny økt analysert · Anbefaling endret: ${workoutTypeLabel(whatChanged?.before_recommendation)} → ${workoutTypeLabel(whatChanged?.after_recommendation)}`
      : "Ny økt analysert · Anbefaling uendret"
    : recChanged
      ? `Anbefaling endret: ${workoutTypeLabel(whatChanged?.before_recommendation)} → ${workoutTypeLabel(whatChanged?.after_recommendation)}`
      : whatChanged?.summary || "Ingen materielle endringer";

  const quality = postSync?.session_quality;
  const comparable = postSync?.comparable;
  const percentile =
    comparable?.percentile != null
      ? `Topp ${Math.round(100 - comparable.percentile)}%`
      : COMPARISON_LABELS[comparable?.comparison_label || ""] || null;

  return (
    <section className="rounded-xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
            Since last update
          </p>
          <h2 className="mt-1 text-lg font-semibold text-slate-900">{headline}</h2>
          {postSync?.activity_name ? (
            <p className="mt-1 text-sm text-slate-600">
              {postSync.activity_name}
              {postSync.session_type ? ` · ${workoutTypeLabel(postSync.session_type)}` : ""}
            </p>
          ) : null}
        </div>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="shrink-0 rounded-md border border-slate-200 px-2 py-1 text-[11px] font-medium text-slate-700"
          aria-expanded={expanded}
        >
          {expanded ? "Skjul" : "Utvid"}
        </button>
      </div>

      {postSync ? (
        <dl className="mt-3 grid gap-2 sm:grid-cols-2 text-sm text-slate-700">
          <div>
            <dt className="text-[11px] uppercase tracking-wide text-slate-500">Session quality</dt>
            <dd className="font-medium">
              {QUALITY_LABELS[quality?.label || "unknown"]}
              {quality?.score != null ? ` (${quality.score})` : ""}
            </dd>
          </div>
          <div>
            <dt className="text-[11px] uppercase tracking-wide text-slate-500">Comparable</dt>
            <dd className="font-medium">{percentile || "For få sammenlignbare"}</dd>
          </div>
          <div>
            <dt className="text-[11px] uppercase tracking-wide text-slate-500">Plan impact</dt>
            <dd className="font-medium">
              {recChanged ? "Anbefaling endret" : postSync.plan_effect?.note || "Ingen endring"}
            </dd>
          </div>
          <div>
            <dt className="text-[11px] uppercase tracking-wide text-slate-500">Next</dt>
            <dd className="font-medium">
              {recChanged
                ? workoutTypeLabel(whatChanged?.after_recommendation)
                : "Se anbefaling under"}
            </dd>
          </div>
        </dl>
      ) : null}

      {expanded ? (
        <div className="mt-4 space-y-3 border-t border-slate-100 pt-3 text-sm">
          <div>
            <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              What changed
            </h3>
            <p className="mt-1 text-slate-700">{whatChanged?.summary || "Ingen materielle signalendringer."}</p>
            {(whatChanged?.material_changes || []).slice(0, 6).map((change) => (
              <p key={change.metric} className="mt-1 text-xs text-slate-600">
                {change.label}: {String(change.before)} → {String(change.after)}
              </p>
            ))}
          </div>
          {postSync?.interpretation ? (
            <div>
              <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                Session analysis
              </h3>
              <p className="mt-1 text-slate-700">{postSync.interpretation}</p>
            </div>
          ) : null}
          <div>
            <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              Why
            </h3>
            <p className="mt-1 text-slate-700">
              Coaching-motoren er kanonisk — denne oppsummeringen gjenspeiler siste sync uten nye
              anbefalinger fra frontend.
            </p>
          </div>
        </div>
      ) : null}

      {postSync?.activity_id ? (
        <Link
          href={`/activities/${postSync.activity_id}`}
          className="mt-3 inline-block text-sm font-medium text-slate-900 underline"
        >
          NEW SESSION ANALYSED → åpne økt
        </Link>
      ) : null}
    </section>
  );
}
