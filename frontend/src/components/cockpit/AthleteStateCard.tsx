"use client";

import Link from "next/link";
import type { AthleteStatePayload } from "@/types/today";
import { trendLabel } from "./cockpitUtils";

function DimensionRow({
  label,
  trend,
  value,
  href,
}: {
  label: string;
  trend?: string | null;
  value?: number | null;
  href?: string;
}) {
  const body = (
    <>
      <p className="text-[11px] font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-sm font-semibold text-slate-900">{trendLabel(trend)}</p>
      {value != null ? <p className="text-xs text-slate-500 tabular-nums">Verdi {value}</p> : null}
      {href ? <p className="mt-1 text-[10px] font-medium text-slate-600">Åpne analyse →</p> : null}
    </>
  );

  if (href) {
    return (
      <Link
        href={href}
        className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2 transition-colors hover:border-slate-300 hover:bg-white"
      >
        {body}
      </Link>
    );
  }

  return <div className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2">{body}</div>;
}

function drilldownFor(key?: string): string | undefined {
  const k = (key || "").toLowerCase();
  if (k.includes("recover") || k.includes("hrv") || k.includes("sleep")) {
    return "/analyse?tab=utvikling&metrics=cardio.hrv_7d,cardio.rhr_7d";
  }
  if (k.includes("threshold") || k.includes("critical") || k.includes("terskel")) {
    return "/analyse?tab=utvikling&metrics=running.critical_speed,fitness.ef_30d";
  }
  if (k.includes("durab") || k.includes("holdbar")) {
    return "/analyse?tab=utvikling&metrics=running.durability_score,fitness.ef_30d";
  }
  if (k.includes("load") || k.includes("ctl") || k.includes("atl") || k.includes("stress")) {
    return "/analyse?tab=utvikling&metrics=fitness.ctl,fitness.atl";
  }
  return "/analyse?tab=utvikling";
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
            href={drilldownFor(dim.key || dim.label)}
          />
        ))}
        {state.durability ? (
          <DimensionRow
            label={state.durability.label}
            trend={state.durability.trend}
            value={state.durability.value}
            href={drilldownFor("durability")}
          />
        ) : null}
      </div>
    </section>
  );
}
