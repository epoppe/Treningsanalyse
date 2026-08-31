"use client";

import { useState } from "react";
import type { RelationshipCardData } from "@/types/analysis";
import { EvidenceBadge } from "./ui";
import { RelationshipDetailPanel } from "./RelationshipDetailPanel";

export function RelationshipCard({
  card,
  period = "1y",
}: {
  card: RelationshipCardData;
  period?: string;
}) {
  const [open, setOpen] = useState(false);

  return (
    <article className="rounded-xl border border-slate-200 bg-white px-3 py-2.5">
      <p className="text-[10px] font-medium uppercase tracking-wide text-slate-500">{card.section}</p>
      <h3 className="mt-0.5 text-sm font-semibold text-slate-900">{card.question}</h3>
      <p className="mt-1 text-xs text-slate-600">
        <span className="font-medium">{card.stimulus.replace(/_/g, " ")}</span>
        {" → "}
        <span className="font-medium">{card.outcome.replace(/_/g, " ")}</span>
      </p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {card.relationship_type ? (
          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-700">
            {card.relationship_type}
          </span>
        ) : null}
        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] capitalize text-slate-700">
          {card.association}
        </span>
        <EvidenceBadge evidence={card.evidence} />
        {card.lag_days != null ? (
          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-700">
            lag {card.lag_days}d
          </span>
        ) : null}
        {card.effect != null ? (
          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-700">
            effekt {card.effect}
          </span>
        ) : null}
        <span className="text-[10px] text-slate-500">n={card.sample_count}</span>
      </div>
      <p className="mt-2 text-xs leading-snug text-slate-600">{card.wording}</p>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="mt-2 text-xs font-medium text-slate-900 underline"
      >
        {open ? "Skjul detalj" : "Åpne relationship detail"}
      </button>
      {open ? <RelationshipDetailPanel card={card} period={period} /> : null}
    </article>
  );
}
