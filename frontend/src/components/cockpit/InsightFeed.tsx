"use client";

import Link from "next/link";
import type { HighlightsPayload } from "@/types/analysis";
import { EvidenceBadge } from "@/components/analysis/ui";
import { trendLabel } from "./cockpitUtils";

export function InsightFeed({ data }: { data?: HighlightsPayload }) {
  const items = data?.highlights?.slice(0, 4) || [];
  if (!items.length) return null;

  return (
    <section className="rounded-xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
      <div className="flex items-center justify-between gap-2">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
            Utvikling
          </p>
          <h2 className="mt-1 text-lg font-semibold text-slate-900">Dette skjer i dataene</h2>
        </div>
        <Link href="/analyse?tab=utvikling" className="text-xs font-medium text-slate-900 underline">
          Åpne analyse
        </Link>
      </div>
      <ul className="mt-3 space-y-2">
        {items.map((item) => (
          <li
            key={`${item.metric}-${item.type}`}
            className="rounded-lg border border-slate-100 px-3 py-2 text-sm"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium text-slate-900">
                {(item.metric || "Metrikk").replace(/_/g, " ")}
              </span>
              {item.direction ? (
                <span className="text-xs text-slate-600">{trendLabel(item.direction)}</span>
              ) : null}
              <EvidenceBadge evidence={item.evidence || "insufficient"} />
            </div>
            {item.summary ? <p className="mt-1 text-xs text-slate-600">{item.summary}</p> : null}
          </li>
        ))}
      </ul>
      {data?.disclaimer ? (
        <p className="mt-2 text-[10px] text-slate-500">{data.disclaimer}</p>
      ) : null}
    </section>
  );
}
