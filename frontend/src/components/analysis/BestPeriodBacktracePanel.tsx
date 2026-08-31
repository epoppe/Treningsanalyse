"use client";

import type { BestPeriodBacktracePayload } from "@/types/analysis";

function isoDaysBefore(isoDate: string, days: number): string {
  const d = new Date(`${isoDate}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

export function BestPeriodBacktracePanel({
  data,
  metric,
  onMetricChange,
  onSelectRange,
}: {
  data?: BestPeriodBacktracePayload;
  metric: string;
  onMetricChange: (m: string) => void;
  onSelectRange?: (from: string, to: string) => void;
}) {
  const options = [
    { key: "fitness.ef_30d", label: "EF30d" },
    { key: "running.critical_speed", label: "Critical speed" },
    { key: "running.durability_score", label: "Durability" },
    { key: "running.speed_20m_hist", label: "Race / 20 min" },
  ];

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="text-sm font-semibold text-slate-900">Beste perioder — tilbakeblikk</h2>
      <p className="mt-0.5 text-[11px] text-slate-500">
        Observasjonelt: hvordan så volum/intensitet ut 4/8/12 uker før sterke utfall? Klikk en
        blokk for å åpne perioden i tidslinjen.
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
              <button
                type="button"
                className="text-left text-xs font-semibold text-slate-900 underline-offset-2 hover:underline"
                onClick={() => {
                  if (!onSelectRange) return;
                  const to = bp.peak_date;
                  const from = isoDaysBefore(to, 27);
                  onSelectRange(from, to);
                }}
              >
                Peak {bp.peak_date} · {bp.peak_value}
              </button>
              <div className="mt-1 grid gap-1 sm:grid-cols-3">
                {bp.preceding_blocks.map((b) => {
                  const clickable = b.status === "ok" && onSelectRange;
                  const to = isoDaysBefore(bp.peak_date, 1);
                  const from = isoDaysBefore(bp.peak_date, b.weeks * 7);
                  const body = (
                    <>
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
                          {clickable ? (
                            <p className="mt-0.5 text-[10px] font-medium text-slate-600">
                              Åpne periode →
                            </p>
                          ) : null}
                        </>
                      )}
                    </>
                  );
                  return clickable ? (
                    <button
                      key={b.weeks}
                      type="button"
                      onClick={() => onSelectRange(from, to)}
                      className="rounded bg-slate-50 px-2 py-1.5 text-left text-[11px] transition-colors hover:bg-slate-100"
                    >
                      {body}
                    </button>
                  ) : (
                    <div key={b.weeks} className="rounded bg-slate-50 px-2 py-1.5 text-[11px]">
                      {body}
                    </div>
                  );
                })}
              </div>
              {bp.wording ? <p className="mt-1 text-[11px] text-slate-500">{bp.wording}</p> : null}
            </li>
          ))}
        </ul>
      )}
      {data?.disclaimer ? (
        <p className="mt-2 text-[11px] text-slate-500">{data.disclaimer}</p>
      ) : (
        <p className="mt-2 text-[11px] text-slate-500">
          OBSERVATIONAL ASSOCIATION — ikke årsaksforklaring eller doseanbefaling.
        </p>
      )}
    </section>
  );
}
