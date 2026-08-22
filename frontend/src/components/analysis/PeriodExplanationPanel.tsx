"use client";

import type { PeriodComparisonRow } from "@/types/analysis";
import { EvidenceBadge } from "./ui";

export function PeriodExplanationPanel({ rows }: { rows: PeriodComparisonRow[] }) {
  const notable = rows
    .filter((r) => r.explanation && r.difference != null && Math.abs(r.difference) >= 0.1)
    .slice(0, 6);

  if (!notable.length) {
    return (
      <p className="mt-2 text-xs text-slate-500">
        Ingen tydelige endringer mellom periodene — små variasjoner er normalt.
      </p>
    );
  }

  return (
    <ul className="mt-2 space-y-2">
      {notable.map((row) => (
        <li key={row.metric} className="rounded-md border border-slate-100 px-2 py-1.5 text-xs">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-slate-800">{row.explanation}</p>
            <EvidenceBadge evidence={row.evidence} />
          </div>
        </li>
      ))}
    </ul>
  );
}
