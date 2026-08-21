"use client";

import Link from "next/link";
import { EmptyState, ErrorState, Skeleton, StatusBadge } from "@/components/coaching/ui-states";
import { useSystemHealth } from "@/hooks/useCoachingDashboard";

export default function SystemPage() {
  const { data, isLoading, isError, error, refetch } = useSystemHealth();

  if (isLoading) return <Skeleton className="h-64 w-full" />;
  if (isError) {
    return (
      <ErrorState
        title="Kunne ikke hente systemstatus"
        description={error instanceof Error ? error.message : undefined}
        onRetry={() => refetch()}
      />
    );
  }
  if (!data) return <EmptyState title="Ingen systemdata" />;

  const healthStatus = data.health?.status || "unknown";
  const integrityStatus = data.integrity?.status || "unknown";
  const issues = data.health?.issues || [];

  return (
    <div className="space-y-3">
      <header>
        <h1 className="text-xl font-semibold tracking-tight md:text-2xl">System / data</h1>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Diagnostikk her — ikke på dagens beslutningsflate.
        </p>
      </header>

      <div className="flex flex-wrap gap-1">
        <StatusBadge
          status={
            healthStatus === "healthy"
              ? "positive"
              : healthStatus === "critical"
                ? "critical"
                : "warning"
          }
          label={`Helse: ${healthStatus}`}
        />
        <StatusBadge
          status={integrityStatus === "healthy" ? "positive" : "warning"}
          label={`Integritet: ${integrityStatus}`}
        />
      </div>

      <section className="rounded-xl border border-border bg-surface px-3 py-2.5">
        <h2 className="text-sm font-semibold">Funn</h2>
        {issues.length === 0 ? (
          <p className="mt-1 text-xs text-muted-foreground">Ingen materialle funn.</p>
        ) : (
          <ul className="mt-1.5 list-disc space-y-0.5 pl-4 text-xs text-muted-foreground">
            {issues.map((i) => (
              <li key={i}>{i}</li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-xl border border-border bg-surface px-3 py-2.5">
        <h2 className="text-sm font-semibold">Verktøy</h2>
        <ul className="mt-1.5 space-y-1 text-xs">
          <li>
            <Link href="/synkronisering" className="text-status-info underline">
              Synkronisering
            </Link>
          </li>
        </ul>
      </section>
    </div>
  );
}
