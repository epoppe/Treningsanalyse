"use client";

import type { DevelopmentPayload, PeriodComparisonPayload } from "@/types/analysis";
import { formatRangeLabel } from "@/lib/analysisRange";
import { AnalysisSkeleton } from "./ui";

function pickRow(rows: PeriodComparisonPayload["rows"] | undefined, keys: string[]) {
  if (!rows?.length) return null;
  return rows.find((r) => keys.includes(r.metric)) || null;
}

function fmt(value?: number | null, digits = 1) {
  if (value == null || Number.isNaN(value)) return "—";
  return Number(value).toFixed(digits);
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h3 className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
        {title}
      </h3>
      <dl className="mt-1.5 space-y-1 text-xs text-slate-700">{children}</dl>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-slate-500">{label}</dt>
      <dd className="font-medium tabular-nums text-slate-900">{value}</dd>
    </div>
  );
}

export function PeriodInspector({
  from,
  to,
  development,
  comparison,
  isLoading,
  onViewWeeks,
  onViewActivities,
  onComparePrevious,
}: {
  from: string;
  to: string;
  development?: DevelopmentPayload;
  comparison?: PeriodComparisonPayload;
  isLoading?: boolean;
  onViewWeeks: () => void;
  onViewActivities: () => void;
  onComparePrevious: () => void;
}) {
  if (isLoading) return <AnalysisSkeleton className="h-56" />;

  const domains = development?.domains || [];
  const byDomain = (key: string) => domains.find((d) => d.domain === key || d.metric === key);

  const ef = byDomain("aerobic_efficiency") || pickRow(comparison?.rows, ["easy_run_efficiency"]);
  const cs = byDomain("threshold") || pickRow(comparison?.rows, ["critical_speed"]);
  const durability = byDomain("durability") || pickRow(comparison?.rows, ["durability"]);
  const hrv = byDomain("recovery") || pickRow(comparison?.rows, ["hrv_rmssd"]);
  const ctl = byDomain("fitness") || pickRow(comparison?.rows, ["ctl"]);
  const atl = byDomain("training_load");
  const consistency = byDomain("consistency");

  const efCurrent =
    ef && "current" in ef
      ? ef.current
      : ef && "period_a" in ef
        ? ef.period_a.value
        : null;
  const csCurrent =
    cs && "current" in cs
      ? cs.current
      : cs && "period_a" in cs
        ? cs.period_a.value
        : null;
  const durCurrent =
    durability && "current" in durability
      ? durability.current
      : durability && "period_a" in durability
        ? durability.period_a.value
        : null;
  const hrvCurrent =
    hrv && "current" in hrv
      ? hrv.current
      : hrv && "period_a" in hrv
        ? hrv.period_a.value
        : null;

  return (
    <aside
      className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm"
      aria-label="Periodeinspektør"
    >
      <header className="border-b border-slate-100 pb-2">
        <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
          Periodeinspektør
        </p>
        <h2 className="mt-1 text-sm font-semibold text-slate-900">
          {formatRangeLabel(from, to)}
        </h2>
        <p className="text-[11px] text-slate-500">
          Observasjonelt sammendrag for valgt vindu — ikke årsaksforklaring.
        </p>
      </header>

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <Section title="Training">
          <Row label="CTL (form)" value={fmt(ctl && "current" in ctl ? ctl.current : null)} />
          <Row label="ATL (belastning)" value={fmt(atl?.current)} />
          <Row label="Konsistens" value={fmt(consistency?.current)} />
          <Row
            label="Endring vs forrige"
            value={
              comparison?.days
                ? `${comparison.days}d vindu`
                : "—"
            }
          />
        </Section>

        <Section title="Performance">
          <Row label="EF" value={fmt(typeof efCurrent === "number" ? efCurrent : null, 2)} />
          <Row label="Critical speed" value={fmt(typeof csCurrent === "number" ? csCurrent : null, 2)} />
          <Row
            label="Holdbarhet"
            value={fmt(typeof durCurrent === "number" ? durCurrent : null, 2)}
          />
          <Row label="LT2 / terskel" value="se terskelmetrikker" />
        </Section>

        <Section title="Recovery">
          <Row label="HRV" value={fmt(typeof hrvCurrent === "number" ? hrvCurrent : null)} />
          <Row label="RHR" value="se restitusjon" />
          <Row label="Søvn" value="se restitusjon" />
        </Section>

        <Section title="Context">
          <Row label="Races / blokker" value="se annotasjoner" />
          <Row label="Merknader" value="historikk-fanen" />
        </Section>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onViewWeeks}
          className="rounded-md bg-slate-900 px-3 py-1.5 text-xs font-medium text-white"
        >
          VIEW WEEKS
        </button>
        <button
          type="button"
          onClick={onViewActivities}
          className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-800"
        >
          VIEW ACTIVITIES
        </button>
        <button
          type="button"
          onClick={onComparePrevious}
          className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-800"
        >
          COMPARE PREVIOUS PERIOD
        </button>
      </div>
    </aside>
  );
}
