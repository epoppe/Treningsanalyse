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
    <div className="space-y-6">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">Fremgang</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Trender først — spesialistsider for grafer.
        </p>
      </header>

      <FormTrendStrip state={data.athlete_state_summary} />

      <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map((c) => (
          <Link
            key={c.label}
            href={c.href || "/training-stress"}
            className="rounded-2xl border border-border bg-surface p-4 transition hover:border-foreground/30"
          >
            <p className="text-xs text-muted-foreground">{c.label}</p>
            <p className="mt-2 text-2xl font-semibold">
              {c.value == null ? "—" : typeof c.value === "number" ? c.value.toFixed(1) : String(c.value)}
            </p>
            <StatusBadge status={c.value == null ? "muted" : "neutral"} label="drill-down" />
          </Link>
        ))}
      </section>

      <section className="rounded-2xl border border-border bg-surface p-5">
        <h2 className="text-lg font-semibold">Spesialistsider</h2>
        <ul className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
          {[
            ["VO₂max", "/vo2max"],
            ["Løpeanalyse", "/analytics"],
            ["Løpsøkonomi", "/ukesanalyse"],
            ["Treningstatus", "/training-status"],
            ["Training Stress", "/training-stress"],
            ["Statistikk", "/statistikk"],
          ].map(([label, href]) => (
            <li key={href}>
              <Link href={href} className="text-sm text-status-info underline-offset-2 hover:underline">
                {label}
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
