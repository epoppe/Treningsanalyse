"use client";

import type { AthleteStatePayload } from "@/types/today";
import { trendLabel } from "./cockpitUtils";

function DimensionRow({
  label,
  trend,
  value,
}: {
  label: string;
  trend?: string | null;
  value?: number | null;
}) {
  return (
    <div className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2">
      <p className="text-[11px] font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-sm font-semibold text-slate-900">{trendLabel(trend)}</p>
      {value != null ? <p className="text-xs text-slate-500 tabular-nums">Verdi {value}</p> : null}
    </div>
  );
}

export function AthleteStateCard({ state }: { state?: AthleteStatePayload }) {
  if (!state) return null;
  const dims = state.dimensions || [];

  return (
    <section className="rounded-xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
      <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
        Utøverstatus
      </p>
      <p className="mt-1 text-lg font-semibold text-slate-900">
        {state.readiness_label || "Status utilgjengelig"}
      </p>
      <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-4">
        {dims.map((dim) => (
          <DimensionRow
            key={dim.key}
            label={dim.label}
            trend={dim.trend}
            value={dim.value}
          />
        ))}
        {state.durability ? (
          <DimensionRow
            label={state.durability.label}
            trend={state.durability.trend}
            value={state.durability.value}
          />
        ) : null}
      </div>
    </section>
  );
}
