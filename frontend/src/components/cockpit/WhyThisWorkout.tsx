"use client";

import { useState } from "react";
import type { DecisionExplanation, DecisionReason } from "@/types/today";
import { EvidenceBadge } from "@/components/analysis/ui";
import { evidenceBand, evidenceLabel } from "./cockpitUtils";

import { reasonTextNb } from "./cockpitUtils";

function reasonText(reason: DecisionReason): string {
  return reasonTextNb(reason);
}

export function WhyThisWorkout({
  explanation,
  fallbackReasons,
  workoutType,
}: {
  explanation?: DecisionExplanation;
  fallbackReasons?: DecisionReason[];
  workoutType?: string;
}) {
  const [level, setLevel] = useState<1 | 2 | 3>(1);
  const top = explanation?.top_reasons || fallbackReasons || [];
  const level1 = top.slice(0, 3);
  const title = workoutType
    ? `Hvorfor ${workoutType.replace(/_/g, " ")} i dag?`
    : "Hvorfor denne økten?";

  return (
    <section className="rounded-xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
            Hvorfor i dag
          </p>
          <h2 className="mt-1 text-lg font-semibold capitalize text-slate-900">{title}</h2>
        </div>
        <div className="flex rounded-lg border border-slate-200 p-0.5 text-[11px]">
          {[1, 2, 3].map((n) => (
            <button
              key={n}
              type="button"
              onClick={() => setLevel(n as 1 | 2 | 3)}
              className={`rounded-md px-2 py-1 ${
                level === n ? "bg-slate-900 text-white" : "text-slate-600"
              }`}
            >
              {n === 1 ? "Kort" : n === 2 ? "Mer" : "Evidens"}
            </button>
          ))}
        </div>
      </div>

      {level === 1 ? (
        <ul className="mt-3 space-y-2">
          {level1.length > 0 ? (
            level1.map((reason, index) => (
              <li key={`${reason.code || index}`} className="flex gap-2 text-sm text-slate-700">
                <span className="text-emerald-600">✓</span>
                <span>{reasonText(reason)}</span>
              </li>
            ))
          ) : (
            <li className="text-sm text-slate-600">
              Anbefalingen er basert primært på konservative standardregler.
            </li>
          )}
        </ul>
      ) : null}

      {level === 2 ? (
        <div className="mt-3 space-y-2 text-sm text-slate-700">
          {top.map((reason, index) => (
            <p key={`${reason.code || index}`}>
              <span className="font-medium">{reason.factor || reason.code || "Signal"}:</span>{" "}
              {reasonText(reason)}
            </p>
          ))}
          {(explanation?.inputs || []).slice(0, 4).map((input, index) => (
            <p key={index} className="text-slate-600">
              {String(input.metric || input.name || "input")}: {String(input.value ?? "—")}
            </p>
          ))}
        </div>
      ) : null}

      {level === 3 ? (
        <div className="mt-3 space-y-3 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <EvidenceBadge evidence={evidenceBand(explanation?.evidence_strength)} />
            <span className="text-slate-600">
              Datakvalitet{" "}
              {explanation?.data_quality != null
                ? `${Math.round(explanation.data_quality * 100)}%`
                : "—"}
            </span>
            <span className="text-slate-600">
              Konfidens{" "}
              {explanation?.decision_confidence != null
                ? `${Math.round(explanation.decision_confidence * 100)}%`
                : "—"}
            </span>
          </div>
          {explanation?.data_freshness ? (
            <div className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
              {Object.entries(explanation.data_freshness)
                .slice(0, 4)
                .map(([metric, payload]) => (
                  <p key={metric}>
                    {metric}: {payload.status || payload.freshness || "ukjent"}
                    {payload.age_days != null ? ` · ${payload.age_days} d siden` : ""}
                  </p>
                ))}
            </div>
          ) : null}
          {explanation?.note ? (
            <p className="text-xs text-slate-500">{explanation.note}</p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
