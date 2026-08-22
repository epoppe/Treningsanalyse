"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { RelationshipLagPayload } from "@/types/analysis";
import {
  ANALYSIS_CHART_AXIS,
  ANALYSIS_CHART_GRID,
  ANALYSIS_CHART_PRIMARY,
  ANALYSIS_CHART_TOOLTIP,
} from "./chartTheme";

export function LagChart({ data }: { data?: RelationshipLagPayload }) {
  const rows =
    data?.profile.map((p) => ({
      lag: `${p.lag_days}d`,
      effect: p.effect_size ?? 0,
      evidence: p.evidence,
    })) || [];

  if (!rows.length) {
    return <p className="text-xs text-slate-500">Ingen lag-profil tilgjengelig.</p>;
  }

  return (
    <div className="h-40 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid {...ANALYSIS_CHART_GRID} />
          <XAxis dataKey="lag" tick={ANALYSIS_CHART_AXIS.tick} />
          <YAxis tick={ANALYSIS_CHART_AXIS.tick} width={32} domain={[-1, 1]} />
          <Tooltip contentStyle={ANALYSIS_CHART_TOOLTIP.contentStyle} />
          <Bar dataKey="effect" fill={ANALYSIS_CHART_PRIMARY} radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
      {data?.best_lag_days != null ? (
        <p className="mt-1 text-[11px] text-slate-500">
          Sterkest observasjon ved lag {data.best_lag_days} dager (ikke anbefalt dose).
        </p>
      ) : null}
    </div>
  );
}
