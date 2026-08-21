"use client";

import Link from "next/link";
import { EmptyState, ErrorState, Skeleton, StatusBadge } from "@/components/coaching/ui-states";
import { useInsightsSummary } from "@/hooks/useCoachingDashboard";

export default function InsightsPage() {
  const { data, isLoading, isError, error, refetch } = useInsightsSummary();

  if (isLoading) return <Skeleton className="h-64 w-full" />;
  if (isError) {
    return (
      <ErrorState
        title="Kunne ikke hente innsikt"
        description={error instanceof Error ? error.message : undefined}
        onRetry={() => refetch()}
      />
    );
  }
  if (!data) return <EmptyState title="Ingen innsikt ennå" />;

  const overall = data.concept_drift?.overall || "insufficient_data";
  const pros = data.prospective?.recommendations as { count?: number; executed?: number } | undefined;

  return (
    <div className="space-y-3">
      <header>
        <h1 className="text-xl font-semibold tracking-tight md:text-2xl">Innsikt</h1>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Oppsummeringer fra backend — ikke lokal spekulasjon.
        </p>
      </header>

      <section className="rounded-xl border border-border bg-surface px-3 py-2.5">
        <h2 className="text-sm font-semibold">Treningsrespons</h2>
        <div className="mt-1.5 flex flex-wrap gap-1">
          <StatusBadge
            status={overall === "confirmed_drift" ? "warning" : overall === "stable" ? "positive" : "muted"}
            label={`Konseptdrift: ${overall}`}
          />
        </div>
        <p className="mt-1.5 text-xs text-muted-foreground">
          {overall === "insufficient_data"
            ? "For lite evidens til å si at responsen er stabil eller endret."
            : overall === "confirmed_drift"
              ? "Noen observerte relasjoner har endret seg — vurder kalibrering via systemet."
              : "Observerte relasjoner ser stabile ut innenfor tilgjengelig evidens."}
        </p>
      </section>

      <section className="rounded-xl border border-border bg-surface px-3 py-2.5">
        <h2 className="text-sm font-semibold">Prospektiv læring</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Anbefalinger: {pros?.count ?? 0} · Utført: {pros?.executed ?? 0}
        </p>
        <p className="mt-0.5 text-[11px] text-muted-foreground">
          Kun registrerte anbefalinger — ikke rekonstruerte backtests.
        </p>
      </section>

      <section className="rounded-xl border border-border bg-surface px-3 py-2.5">
        <h2 className="text-sm font-semibold">Dypere innsikt</h2>
        <ul className="mt-1.5 grid grid-cols-2 gap-1 sm:grid-cols-3">
          {[
            ["HRV", "/hrv"],
            ["Søvn", "/sovn"],
            ["Stress", "/stress"],
            ["Body Battery", "/body-battery"],
            ["Sammenhenger", "/sammenhenger"],
            ["Daglig readiness", "/daglig-readiness"],
            ["System", "/system"],
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
