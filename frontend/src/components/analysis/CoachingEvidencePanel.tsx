"use client";

import Link from "next/link";
import { useState } from "react";
import { EvidenceBadge, AnalysisEmpty, AnalysisError, AnalysisSkeleton } from "@/components/analysis/ui";
import { useCoachingEvidence } from "@/hooks/useCoachingEvidence";
import type { CoachingEvidencePayload, CoachingTypeEvidence } from "@/types/coachingEvidence";

const WINDOWS = [30, 90, 180, 365];

function percent(value: number | null | undefined): string {
  if (value == null) return "–";
  return `${Math.round(value * 100)} %`;
}

function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-3 py-3">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-lg font-semibold text-slate-900">{value}</p>
    </div>
  );
}

function TypeCard({
  row,
  open,
  onToggle,
}: {
  row: CoachingTypeEvidence;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <article className="rounded-xl border border-slate-200 bg-white px-3 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-900">{row.label}</h3>
        <EvidenceBadge evidence={(row.evidence_level || "insufficient").toLowerCase()} />
      </div>
      <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-slate-600 sm:grid-cols-3">
        <div>Anbefalinger {row.recommendation_count}</div>
        <div>Utførelse {row.execution_count}</div>
        <div>Modne utfall {row.mature_outcome_count}</div>
        <div>Pending {row.pending_count}</div>
        <div>Incomplete {row.incomplete_count}</div>
        <div>Feedback {row.feedback_count}</div>
      </dl>
      <button type="button" className="mt-2 text-xs font-medium text-slate-900 underline" onClick={onToggle}>
        {open ? "Skjul observasjoner" : "Vis observasjoner"}
      </button>
      {open ? (
        <ul className="mt-2 space-y-1 text-xs text-slate-700">
          {row.observations.length === 0 ? <li>Ingen observasjoner i vinduet.</li> : null}
          {row.observations.map((item) => (
            <li key={`${item.recommendation_id}-${item.as_of_date}`}>
              {item.as_of_date} · {item.execution_status || "ukjent"} · {item.short_term_maturity || "–"}
              {item.match_source ? ` · ${item.match_source}` : ""}
              {item.activity_id ? (
                <>
                  {" "}
                  <Link className="underline" href={`/activities/${item.activity_id}`}>
                    Åpne økt
                  </Link>
                </>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </article>
  );
}

export function CoachingEvidenceView({
  data,
  windowDays,
  onWindow,
}: {
  data: CoachingEvidencePayload;
  windowDays: number;
  onWindow: (days: number) => void;
}) {
  const [openType, setOpenType] = useState<string | null>(null);
  const overview = data.overview;
  const empty = overview.canonical_recommendation_count === 0;

  return (
    <div className="space-y-4">
      <header className="space-y-2">
        <h2 className="text-lg font-semibold text-slate-900">Lærer coachen faktisk av treningen din?</h2>
        <p className="text-sm text-slate-600">
          Prospektiv observasjon i valgt vindu. Vinduet endrer ikke modeller eller kalibrering.
        </p>
        <div className="flex flex-wrap gap-2">
          {(data.period.allowed_windows || WINDOWS).map((days) => (
            <button
              key={days}
              type="button"
              onClick={() => onWindow(days)}
              className={
                days === windowDays
                  ? "rounded-md bg-slate-900 px-2 py-1 text-[11px] font-medium text-white"
                  : "rounded-md bg-white px-2 py-1 text-[11px] font-medium text-slate-700 ring-1 ring-slate-200"
              }
            >
              {days === 365 ? "1 år" : `${days} dager`}
            </button>
          ))}
        </div>
      </header>

      <section className="grid grid-cols-2 gap-2 md:grid-cols-5">
        <SummaryCard label="Prospektive anbefalinger" value={String(overview.canonical_recommendation_count)} />
        <SummaryCard label="Modne short-term outcomes" value={String(overview.short_term_outcome_count)} />
        <SummaryCard label="Personlig evidens" value={overview.evidence_label} />
        <SummaryCard label="Feedback-dekning" value={percent(overview.feedback_coverage)} />
        <SummaryCard label="Eksplisitt activity matching" value={percent(overview.explicit_matching_share)} />
      </section>

      {empty ? (
        <AnalysisEmpty
          title="Ingen kanoniske anbefalinger i vinduet"
          description="Pending og manglende data er ikke et negativt utfall."
        />
      ) : null}

      <section className="grid gap-2 md:grid-cols-3">
        {data.maturity_legend.map((item) => (
          <div key={item.status} className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
            <p className="text-xs font-semibold text-slate-900">{item.label}</p>
            <p className="mt-1 text-xs text-slate-600">{item.text}</p>
          </div>
        ))}
      </section>

      <section className="space-y-2">
        <h3 className="text-sm font-semibold text-slate-900">Hva systemet har lært om deg</h3>
        {data.what_we_know.length === 0 ? (
          <AnalysisEmpty title="Ingen støttet eller fremvoksende læring i vinduet" />
        ) : (
          data.what_we_know.map((item) => (
            <p key={item.workout_type || item.text} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700">
              {item.text}
            </p>
          ))
        )}
      </section>

      <section className="space-y-2">
        <h3 className="text-sm font-semibold text-slate-900">Hva systemet fortsatt ikke vet</h3>
        {data.what_we_do_not_know.map((item) => (
          <p key={`${item.code}-${item.workout_type || "all"}`} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700">
            {item.text}
          </p>
        ))}
      </section>

      <section className="space-y-2">
        <h3 className="text-sm font-semibold text-slate-900">Effekt og gjennomføring</h3>
        <p className="text-xs text-slate-500">{data.feasibility.note}</p>
        <p className="text-xs text-slate-600">
          Fulgt {data.feasibility.followed} · Justert {data.feasibility.modified} · Erstattet {data.feasibility.replaced} · Hoppet over {data.feasibility.skipped} · Venter {data.feasibility.pending}
        </p>
        <div className="grid gap-2 md:grid-cols-2">
          {data.effectiveness.map((row) => (
            <TypeCard
              key={row.workout_type}
              row={row}
              open={openType === row.workout_type}
              onToggle={() => setOpenType(openType === row.workout_type ? null : row.workout_type)}
            />
          ))}
        </div>
      </section>

      <section className="grid gap-2 md:grid-cols-2">
        <div className="rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm text-slate-700">
          <h3 className="font-semibold text-slate-900">Confidence</h3>
          <p className="mt-1">Status {data.confidence.status}</p>
          <p>N {data.confidence.sample_count}</p>
          <p>Brier {data.confidence.brier_score ?? "–"}</p>
          <p>Kalibreringsfeil {data.confidence.expected_calibration_error ?? "–"}</p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm text-slate-700">
          <h3 className="font-semibold text-slate-900">Evidenskvalitet</h3>
          <p className="mt-1">
            Rå N {data.evidence_quality.raw_sample_count} · effektiv N {data.evidence_quality.effective_sample_count}
          </p>
          <p>Spredning {data.evidence_quality.spread_days ?? "–"} dager · {data.evidence_quality.sufficiency_label}</p>
          <p>
            Eksplisitt {data.evidence_quality.explicit_execution_matches} · heuristisk {data.evidence_quality.legacy_heuristic_matches}
          </p>
          <p>
            Pending {data.evidence_quality.pending_windows} · incomplete {data.evidence_quality.incomplete_windows}
          </p>
        </div>
      </section>

      <section className="grid gap-2 md:grid-cols-2">
        <div className="rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm text-slate-700">
          <h3 className="font-semibold text-slate-900">Objektive signaler</h3>
          <p className="mt-1">{data.signals.objective.sources.join(", ")}</p>
          <p>Korttid N {data.signals.objective.short_term_sample_count}</p>
          <p>Sesjonskvalitet N {data.signals.objective.session_quality_sample_count}</p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm text-slate-700">
          <h3 className="font-semibold text-slate-900">Subjektive signaler</h3>
          <p className="mt-1">{data.signals.subjective.sources.join(", ")}</p>
          <p>N {data.signals.subjective.sample_count} · dekning {percent(data.signals.subjective.coverage)}</p>
          <p>Kilde {data.signals.subjective.provenance}. Ikke fasit.</p>
        </div>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white px-3 py-3">
        <h3 className="text-sm font-semibold text-slate-900">Dette bør ikke endres ennå</h3>
        <ul className="mt-2 list-disc space-y-1 pl-4 text-sm text-slate-700">
          {data.do_not_change.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
        <p className="mt-2 text-xs text-slate-500">
          Skygge: {data.operations.shadow.status}. {data.operations.shadow.note}
        </p>
      </section>
    </div>
  );
}

export function CoachingEvidencePanel() {
  const [windowDays, setWindowDays] = useState(90);
  const query = useCoachingEvidence(windowDays);

  if (query.isLoading) {
    return (
      <div className="space-y-2" role="status" aria-label="Laster coaching-evidens">
        <AnalysisSkeleton className="h-8 w-2/3" />
        <AnalysisSkeleton className="h-24 w-full" />
      </div>
    );
  }
  if (query.isError) {
    return (
      <AnalysisError
        title="Kunne ikke laste coaching-evidens"
        description={query.error instanceof Error ? query.error.message : undefined}
        onRetry={() => query.refetch()}
      />
    );
  }
  if (!query.data) {
    return <AnalysisEmpty title="Ingen evidens å vise" />;
  }
  return <CoachingEvidenceView data={query.data} windowDays={windowDays} onWindow={setWindowDays} />;
}
