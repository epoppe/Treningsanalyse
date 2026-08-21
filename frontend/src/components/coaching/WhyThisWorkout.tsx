"use client";

import { useState } from "react";
import type { DecisionExplanation, DecisionReason } from "@/types/coaching";
import { reasonLabel } from "@/lib/coachingLabels";

function scoreLabel(n?: number | null): string {
  if (n == null || !Number.isFinite(n)) return "—";
  if (n >= 0.7) return `høy (${n.toFixed(2)})`;
  if (n >= 0.45) return `moderat (${n.toFixed(2)})`;
  return `lav (${n.toFixed(2)})`;
}

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
    new Set([
      ...(guardrails || []),
      ...(explanation?.guardrails || []),
      ...(explanation?.guardrails_triggered || []),
    ])
  );
  const freshnessEntries = Object.entries(explanation?.data_freshness || {}).slice(0, 6);

  return (
    <section id="why-workout" aria-labelledby="why-heading" className="rounded-xl border border-border bg-surface px-3 py-2.5">
      <div className="flex items-center justify-between gap-2">
        <h2 id="why-heading" className="text-sm font-semibold text-foreground">
          Hvorfor
        </h2>
        <button
          type="button"
          className="inline-flex min-h-8 items-center rounded-md px-2 py-1 text-xs font-medium text-status-info hover:underline"
          aria-expanded={open}
          aria-controls="why-details"
          onClick={() => setOpen((v) => !v)}
        >
          {open ? "Skjul" : "Vis mer"}
        </button>
      </div>
      {unique.length === 0 ? (
        <p className="mt-1 text-xs text-muted-foreground">Ingen begrunnelseskoder tilgjengelig.</p>
      ) : (
        <ul className="mt-1.5 flex flex-wrap gap-1">
          {unique.map((code) => {
            const isWarn =
              guards.includes(code) ||
              code.includes("LOW") ||
              code.includes("STALE") ||
              code.includes("MISSING");
            return (
              <li
                key={code}
                className={
                  isWarn
                    ? "rounded-md border border-status-warning/40 bg-status-warning/10 px-2 py-0.5 text-xs text-foreground"
                    : "rounded-md border border-status-positive/30 bg-status-positive/10 px-2 py-0.5 text-xs text-foreground"
                }
              >
                <span aria-hidden>{isWarn ? "! " : "✓ "}</span>
                {reasonLabel(code)}
              </li>
            );
          })}
        </ul>
      )}
      {open ? (
        <div
          id="why-details"
          className="mt-2 space-y-1 rounded-lg bg-surface-muted p-2 text-xs text-muted-foreground"
          data-testid="why-details"
        >
          <p>
            Evidensstyrke:{" "}
            <span className="text-foreground">{scoreLabel(explanation?.evidence_strength)}</span>
          </p>
          <p>
            Beslutningstillit:{" "}
            <span className="text-foreground">{scoreLabel(explanation?.decision_confidence)}</span>
          </p>
          <p>
            Datakvalitet:{" "}
            <span className="text-foreground">
              {typeof explanation?.data_quality === "number"
                ? scoreLabel(explanation.data_quality)
                : "—"}
            </span>
          </p>
          {guards.length ? (
            <div>
              <p className="font-medium text-foreground">Guardrails</p>
              <ul className="mt-0.5 list-disc space-y-0.5 pl-4">
                {guards.map((g) => (
                  <li key={g}>{reasonLabel(g)}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {freshnessEntries.length ? (
            <ul className="mt-1 space-y-0.5 border-t border-border pt-1">
              {freshnessEntries.map(([key, entry]) => (
                <li key={key}>
                  {key}: {entry.status || entry.freshness || "—"}
                  {entry.age_days != null ? ` · ${Math.round(entry.age_days)} d` : ""}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
