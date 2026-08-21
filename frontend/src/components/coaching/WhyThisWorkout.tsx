"use client";

import { useState } from "react";
import type { DecisionExplanation, DecisionReason } from "@/types/coaching";
import { reasonLabel } from "@/lib/coachingLabels";

export function WhyThisWorkout({
  reasons,
  explanation,
  guardrails,
}: {
  reasons?: DecisionReason[] | null;
  explanation?: DecisionExplanation | null;
  guardrails?: string[] | null;
}) {
  const [open, setOpen] = useState(false);
  const codes =
    explanation?.reason_codes?.length
      ? explanation.reason_codes
      : (reasons || []).map((r) => r.code).filter(Boolean);
  const unique = Array.from(new Set(codes)).slice(0, 6);
  const guards = Array.from(
    new Set([...(guardrails || []), ...(explanation?.guardrails || [])])
  );

  return (
    <section id="why-workout" aria-labelledby="why-heading" className="rounded-2xl border border-border bg-surface p-5">
      <h2 id="why-heading" className="text-lg font-semibold text-foreground">
        Hvorfor
      </h2>
      {unique.length === 0 ? (
        <p className="mt-2 text-sm text-muted-foreground">Ingen begrunnelseskoder tilgjengelig.</p>
      ) : (
        <ul className="mt-3 flex flex-wrap gap-2">
          {unique.map((code) => {
            const isWarn = guards.includes(code) || code.includes("LOW") || code.includes("STALE") || code.includes("MISSING");
            return (
              <li
                key={code}
                className={
                  isWarn
                    ? "rounded-full border border-status-warning/40 bg-status-warning/10 px-3 py-1 text-sm text-foreground"
                    : "rounded-full border border-status-positive/30 bg-status-positive/10 px-3 py-1 text-sm text-foreground"
                }
              >
                <span aria-hidden>{isWarn ? "! " : "✓ "}</span>
                {reasonLabel(code)}
              </li>
            );
          })}
        </ul>
      )}
      <button
        type="button"
        className="mt-4 text-sm font-medium text-status-info underline-offset-2 hover:underline"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {open ? "Skjul detaljer" : "Vis mer"}
      </button>
      {open ? (
        <div className="mt-3 space-y-2 rounded-xl bg-surface-muted p-3 text-sm text-muted-foreground">
          <p>
            Evidensstyrke:{" "}
            <span className="text-foreground">
              {explanation?.evidence_strength ?? "—"}
            </span>
          </p>
          <p>
            Beslutningstillit:{" "}
            <span className="text-foreground">
              {explanation?.decision_confidence ?? "—"}
            </span>
          </p>
          <p>
            Datakvalitet:{" "}
            <span className="text-foreground">
              {typeof explanation?.data_quality === "number"
                ? explanation.data_quality
                : "—"}
            </span>
          </p>
          {guards.length ? (
            <p>Guardrails: {guards.map(reasonLabel).join(" · ")}</p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
