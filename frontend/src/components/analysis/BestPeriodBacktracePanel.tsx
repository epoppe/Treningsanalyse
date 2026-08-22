"use client";

import type { BestPeriodBacktracePayload } from "@/types/analysis";

export function BestPeriodBacktracePanel({
  data,
  metric,
  onMetricChange,
}: {
  data?: BestPeriodBacktracePayload;
  metric: string;
  onMetricChange: (m: string) => void;
}) {
  const options = [
    { key: "fitness.ef_30d", label: "EF30d" },
    { key: "running.critical_speed", label: "Critical speed" },
    { key: "running.durability_score", label: "Durability" },
    { key: "running.speed_20m_hist", label: "20 min best" },
  ];

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-3">
      <h2 className="text-sm font-semibold text-slate-900">Beste perioder — tilbakeblikk</h2>
      <p className="mt-0.5 text-[11px] text-slate-500">
        Hvordan så treningen ut 4/8/12 uker før historisk sterke perioder?
      </p>
      <div className="mt-2 flex flex-wrap gap-1">
        {options.map((o) => (
          <button
            key={o.key}
            type="button"
            onClick={() => onMetricChange(o.key)}
            className={
              metric === o.key
                ? "rounded-md bg-slate-900 px-2 py-1 text-[11px] font-medium text-white"
                : "rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-[11px] text-slate-700"
            }
          >
            {o.label}
          </button>
        ))}
      </div>
      {data?.status === "insufficient" || !data?.best_periods?.length ? (
        <p className="mt-3 text-xs text-slate-500">
          {data?.note || "Utilstrekkelig data for tilbakeblikk."}
        </p>
      ) : (
        <ul className="mt-3 space-y-2">
          {data.best_periods.map((bp) => (
            <li key={bp.peak_date} className="rounded-md border border-slate-100 px-2 py-2">
              <p className="text-xs font-semibold text-slate-900">
                Peak {bp.peak_date} · {bp.peak_value}
              </p>
              <div className="mt-1 grid gap-1 sm:grid-cols-3">
                {bp.preceding_blocks.map((b) => (
                  <div key={b.weeks} className="rounded bg-slate-50 px-2 py-1.5 text-[11px]">
                    <p className="font-medium text-slate-700">{b.weeks} uker før</p>
                    {b.status !== "ok" ? (
                      <p className="text-slate-500">utilstrekkelig</p>
                    ) : (
                      <>
                        <p className="tabular-nums text-slate-600">
                          TSS {b.total_tss ?? "—"} · økter {b.activity_count ?? "—"}
                        </p>
                        <p className="tabular-nums text-slate-500">
                          snitt/uke{" "}
                          {b.avg_weekly_duration_seconds != null
                            ? `${Math.round(b.avg_weekly_duration_seconds / 60)} min`
                            : "—"}
                        </p>
                      </>
                    )}
                  </div>
                ))}
              </div>
              {bp.wording ? <p className="mt-1 text-[11px] text-slate-500">{bp.wording}</p> : null}
            </li>
          ))}
        </ul>
      )}
      {data?.disclaimer ? (
        <p className="mt-2 text-[11px] text-slate-500">{data.disclaimer}</p>
      ) : null}
    </section>
  );
}
