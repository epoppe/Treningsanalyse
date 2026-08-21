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
    <div className="space-y-6">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">System / data</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Diagnostikk holdes her — ikke på dagens beslutningsflate.
        </p>
      </header>

      <div className="flex flex-wrap gap-2">
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

      <section className="rounded-2xl border border-border bg-surface p-5">
        <h2 className="text-lg font-semibold">Funn</h2>
        {issues.length === 0 ? (
          <p className="mt-2 text-sm text-muted-foreground">Ingen materialle funn.</p>
        ) : (
          <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
            {issues.map((i) => (
              <li key={i}>{i}</li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-2xl border border-border bg-surface p-5">
        <h2 className="text-lg font-semibold">Verktøy</h2>
        <ul className="mt-3 space-y-2 text-sm">
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
