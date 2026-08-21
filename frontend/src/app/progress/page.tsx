"use client";

import Link from "next/link";
import { FormTrendStrip } from "@/components/coaching/FormTrendStrip";
import { EmptyState, ErrorState, Skeleton, StatusBadge } from "@/components/coaching/ui-states";
import { useProgressSummary } from "@/hooks/useCoachingDashboard";

export default function ProgressPage() {
  const { data, isLoading, isError, error, refetch } = useProgressSummary();

  if (isLoading) return <Skeleton className="h-64 w-full" />;
  if (isError) {
    return (
      <ErrorState
        title="Kunne ikke hente fremgang"
        description={error instanceof Error ? error.message : undefined}
        onRetry={() => refetch()}
      />
    );
  }
  if (!data) {
    return <EmptyState title="Ingen fremgangsdata" />;
  }

  const cards = [
    { label: "CTL (form)", value: data.ctl, href: data.drill_down?.load },
    { label: "ATL (belastning)", value: data.atl, href: data.drill_down?.load },
    { label: "TSB (overskudd)", value: data.tsb, href: data.drill_down?.load },
    { label: "HRV Δ%", value: data.hrv_delta_pct, href: "/hrv" },
  ];

  return (
    <div className="space-y-3">
      <header>
        <h1 className="text-xl font-semibold tracking-tight md:text-2xl">Fremgang</h1>
        <p className="mt-0.5 text-xs text-muted-foreground">Trender først — grafer via drill-down.</p>
      </header>

      <FormTrendStrip state={data.athlete_state_summary} />

      <section className="grid grid-cols-2 gap-1.5 lg:grid-cols-4">
        {cards.map((c) => (
          <Link
            key={c.label}
            href={c.href || "/training-stress"}
            className="rounded-xl border border-border bg-surface px-2.5 py-2 transition hover:border-foreground/30"
          >
            <p className="text-[10px] text-muted-foreground">{c.label}</p>
            <p className="mt-0.5 text-lg font-semibold tabular-nums">
              {c.value == null ? "—" : typeof c.value === "number" ? c.value.toFixed(1) : String(c.value)}
            </p>
            <StatusBadge status={c.value == null ? "muted" : "neutral"} label="drill-down" />
          </Link>
        ))}
      </section>

      <section className="rounded-xl border border-border bg-surface px-3 py-2.5">
        <h2 className="text-sm font-semibold">Spesialistsider</h2>
        <ul className="mt-1.5 grid grid-cols-2 gap-1 sm:grid-cols-3">
          {[
            ["VO₂max", "/vo2max"],
            ["Løpeanalyse", "/analytics"],
            ["Løpsøkonomi", "/ukesanalyse"],
            ["Treningstatus", "/training-status"],
            ["Training Stress", "/training-stress"],
            ["Statistikk", "/statistikk"],
          ].map(([label, href]) => (
            <li key={href}>
              <Link href={href} className="text-xs text-status-info underline-offset-2 hover:underline">
                {label}
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
