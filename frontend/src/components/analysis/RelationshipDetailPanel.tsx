"use client";

import type { RelationshipCardData } from "@/types/analysis";
import { useRelationshipLag } from "@/hooks/useAnalysisWorkspace";
import { LagChart } from "./LagChart";
import { AnalysisSkeleton } from "./ui";

export function RelationshipDetailPanel({
  card,
  period,
}: {
  card: RelationshipCardData;
  period: string;
}) {
  const lag = useRelationshipLag(card.stimulus, card.outcome, period, Boolean(card.stimulus && card.outcome));

  return (
    <div className="mt-3 rounded-lg border border-slate-100 bg-slate-50/80 p-3">
      <p className="text-xs font-semibold text-slate-800">Lag-profil</p>
      <p className="text-[11px] text-slate-500">
        Hvordan assosiasjonen varierer med forsinkelse — observasjonelt, ikke kausal.
      </p>
      {lag.isLoading ? <AnalysisSkeleton className="mt-2 h-32" /> : null}
      {lag.data ? <LagChart data={lag.data} /> : null}
      {card.lag_days != null ? (
        <p className="mt-1 text-[11px] text-slate-600">
          Historisk beste lag i kortet: {card.lag_days} dager
        </p>
      ) : null}
    </div>
  );
}
