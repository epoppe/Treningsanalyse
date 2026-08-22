"use client";

import Link from "next/link";
import { useCallback, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type {
  AnalysisPeriod,
  AnalysisSession,
  AnalysisSport,
  AnalysisTab,
} from "@/types/analysis";
import { cn } from "@/lib/utils";

const PERIODS: AnalysisPeriod[] = ["28d", "90d", "6m", "1y", "2y", "all"];
const SPORTS: AnalysisSport[] = ["running", "cycling", "all"];
const SESSIONS: AnalysisSession[] = ["all", "easy", "long", "threshold", "vo2", "race"];
const TABS: Array<{ id: AnalysisTab; label: string }> = [
  { id: "utvikling", label: "Utvikling" },
  { id: "sammenhenger", label: "Sammenhenger" },
  { id: "historikk", label: "Historikk" },
];

function parseTab(v: string | null): AnalysisTab {
  if (v === "sammenhenger" || v === "historikk" || v === "utvikling") return v;
  return "utvikling";
}

function parsePeriod(v: string | null): AnalysisPeriod {
  return (PERIODS.includes(v as AnalysisPeriod) ? v : "90d") as AnalysisPeriod;
}

function parseSport(v: string | null): AnalysisSport {
  return (SPORTS.includes(v as AnalysisSport) ? v : "running") as AnalysisSport;
}

function parseSession(v: string | null): AnalysisSession {
  return (SESSIONS.includes(v as AnalysisSession) ? v : "all") as AnalysisSession;
}

export function useAnalysisUrlState() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const state = useMemo(
    () => ({
      tab: parseTab(searchParams.get("tab")),
      period: parsePeriod(searchParams.get("period")),
      sport: parseSport(searchParams.get("sport")),
      session: parseSession(searchParams.get("session")),
      metrics: (searchParams.get("metrics") || "fitness.ctl,cardio.hrv_7d")
        .split(",")
        .map((m) => m.trim())
        .filter(Boolean)
        .slice(0, 4),
      outcome: searchParams.get("outcome") || "fitness.ef_30d",
      preset: searchParams.get("preset") || "",
      backtrace: searchParams.get("backtrace") || "fitness.ef_30d",
      week: searchParams.get("week") || "",
    }),
    [searchParams]
  );

  const setParams = useCallback(
    (patch: Record<string, string | null>) => {
      const next = new URLSearchParams(searchParams.toString());
      Object.entries(patch).forEach(([k, v]) => {
        if (v == null || v === "") next.delete(k);
        else next.set(k, v);
      });
      router.replace(`${pathname}?${next.toString()}`, { scroll: false });
    },
    [pathname, router, searchParams]
  );

  return { state, setParams };
}

function Chip({
  active,
  children,
  onClick,
}: {
  active: boolean;
  children: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-md px-2 py-1 text-[11px] font-medium",
        active ? "bg-slate-900 text-white" : "bg-white text-slate-700 ring-1 ring-slate-200"
      )}
    >
      {children}
    </button>
  );
}

export function AnalysisFiltersBar() {
  const { state, setParams } = useAnalysisUrlState();

  return (
    <div className="space-y-2 rounded-lg border border-slate-200 bg-slate-50/80 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
          Periode
        </span>
        {PERIODS.map((p) => (
          <Chip key={p} active={state.period === p} onClick={() => setParams({ period: p })}>
            {p}
          </Chip>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
          Sport
        </span>
        {SPORTS.map((s) => (
          <Chip key={s} active={state.sport === s} onClick={() => setParams({ sport: s })}>
            {s}
          </Chip>
        ))}
        <span className="ml-2 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
          Kontekst
        </span>
        {SESSIONS.map((s) => (
          <Chip key={s} active={state.session === s} onClick={() => setParams({ session: s })}>
            {s}
          </Chip>
        ))}
      </div>
      <p className="text-[11px] text-slate-500">
        Filter lagres i URL. Sport/kontekst brukes mer i senere drill-downs — trender følger periode nå.{" "}
        <Link href="/sammenhenger" className="underline">
          Avansert scatter
        </Link>
      </p>
    </div>
  );
}

export function AnalysisTabs() {
  const { state, setParams } = useAnalysisUrlState();
  return (
    <nav className="flex gap-1 border-b border-slate-200" aria-label="Analysefaner">
      {TABS.map((t) => (
        <button
          key={t.id}
          type="button"
          onClick={() => setParams({ tab: t.id })}
          className={cn(
            "-mb-px border-b-2 px-3 py-2 text-sm font-medium",
            state.tab === t.id
              ? "border-slate-900 text-slate-900"
              : "border-transparent text-slate-500 hover:text-slate-800"
          )}
          aria-current={state.tab === t.id ? "page" : undefined}
        >
          {t.label}
        </button>
      ))}
    </nav>
  );
}
