"use client";

import type { DevelopmentDomain } from "@/types/analysis";
import { EvidenceBadge } from "./ui";

function arrow(direction?: string) {
  const d = (direction || "").toLowerCase();
  if (d === "improving") return "↑";
  if (d === "declining") return "↓";
  if (d === "uncertain") return "?";
  return "→";
}

export function TrendSummaryCard({ domain }: { domain: DevelopmentDomain }) {
  const change =
    domain.relative_change_pct == null
      ? "—"
      : `${domain.relative_change_pct > 0 ? "+" : ""}${domain.relative_change_pct.toFixed(1)}%`;

  return (
    <article className="rounded-lg border border-slate-200 bg-white px-3 py-2.5 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-900">{domain.label}</h3>
        <span className="text-base" aria-hidden>
          {arrow(domain.direction)}
        </span>
      </div>
      <p className="mt-1 text-lg font-semibold tabular-nums text-slate-800">{change}</p>
      <p className="text-xs text-slate-500">
        {domain.direction_label || "Usikker"}
        {domain.current != null ? ` · nå ${Number(domain.current).toFixed(1)}` : ""}
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <EvidenceBadge evidence={domain.evidence} />
        <span className="text-[10px] text-slate-500">n={domain.sample_count}</span>
        {domain.change_point_detected ? (
          <span className="text-[10px] font-medium text-amber-700">endringspunkt</span>
        ) : null}
      </div>
    </article>
  );
}
