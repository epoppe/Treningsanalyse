"use client";

import {
  Bar,
  BarChart,
  ResponsiveContainer,
} from "recharts";
import type { RelationshipLagPayload } from "@/types/analysis";
import { CHART_MARGIN, CHART_PRIMARY } from "@/components/charts/chartTheme";
import {
  ThemedCartesianGrid,
  ThemedTooltip,
  ThemedXAxis,
  ThemedYAxis,
} from "@/components/charts/ThemedRecharts";
import { axisLabelProps } from "@/lib/chartFormatters";

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
        <BarChart data={rows} margin={CHART_MARGIN.compact}>
          <ThemedCartesianGrid />
          <ThemedXAxis dataKey="lag" />
          <ThemedYAxis
            width={36}
            domain={[-1, 1]}
            label={axisLabelProps("Effektstørrelse")}
          />
          <ThemedTooltip
            formatter={(value: any) => [Number(value).toFixed(2), "Effekt"]}
            labelFormatter={(label) => `Lag: ${label}`}
          />
          <Bar dataKey="effect" fill={CHART_PRIMARY} radius={[4, 4, 0, 0]} />
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
