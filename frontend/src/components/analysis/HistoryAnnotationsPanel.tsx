"use client";

import type { HistoryAnnotationsPayload } from "@/types/analysis";
import { planReasonLabel } from "@/components/cockpit/cockpitUtils";
import { AnalysisSkeleton } from "./ui";

const TYPE_LABELS: Record<string, string> = {
  plan_adjustment: "Plan",
  recommendation_change: "Anbefaling",
};

export function HistoryAnnotationsPanel({
  data,
  isLoading,
}: {
  data?: HistoryAnnotationsPayload;
  isLoading?: boolean;
}) {
  if (isLoading) return <AnalysisSkeleton className="h-32" />;
  const items = data?.items || [];
  if (!items.length) {
    return (
      <p className="text-sm text-slate-500">
        Ingen registrerte milepæler ennå — plan- og anbefalingsendringer vises her.
      </p>
    );
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-3">
      <h2 className="text-sm font-semibold text-slate-900">Milepæler og notater</h2>
      <ol className="mt-2 space-y-2">
        {items.map((item, index) => (
          <li key={`${item.date}-${item.type}-${index}`} className="rounded-md border border-slate-100 px-2 py-1.5">
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="rounded bg-slate-100 px-1.5 py-0.5 font-medium text-slate-700">
                {TYPE_LABELS[item.type || ""] || item.type}
              </span>
              {item.date ? (
                <time className="text-slate-500 tabular-nums">
                  {new Intl.DateTimeFormat("nb-NO", {
                    day: "numeric",
                    month: "short",
                    year: "numeric",
                  }).format(new Date(item.date))}
                </time>
              ) : null}
            </div>
            <p className="mt-1 text-sm font-medium text-slate-900">{item.title}</p>
            {item.detail ? (
              <p className="text-xs text-slate-600">
                {item.type === "plan_adjustment" ? planReasonLabel(item.detail) : item.detail}
              </p>
            ) : null}
          </li>
        ))}
      </ol>
      {data?.disclaimer ? <p className="mt-2 text-[10px] text-slate-500">{data.disclaimer}</p> : null}
    </section>
  );
}
