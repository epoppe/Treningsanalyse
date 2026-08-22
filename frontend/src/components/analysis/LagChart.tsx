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
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="lag" tick={{ fontSize: 10 }} />
          <YAxis tick={{ fontSize: 10 }} width={32} domain={[-1, 1]} />
          <Tooltip contentStyle={{ fontSize: 12 }} />
          <Bar dataKey="effect" fill="#0f766e" radius={[4, 4, 0, 0]} />
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
