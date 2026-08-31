"use client";

import { useState, useEffect, type ReactNode } from "react";
import { analysisApi } from "../utils/api";
import { apiErrorMessage, classifyApiError } from "../utils/apiErrors";
import { initialMetricState, type MetricState } from "../utils/metricState";
import { cn } from "@/lib/utils";

interface NegativeSplitData {
  activity_id: number;
  negative_split_percent: number;
  first_half_pace: number;
  second_half_pace: number;
  data_points: number;
  calculation_method: string;
}

interface DecouplingData {
  activity_id: number;
  decoupling_percent: number;
  first_half_hr: number;
  first_half_speed: number;
  second_half_hr: number;
  second_half_speed: number;
  first_half_ratio: number;
  second_half_ratio: number;
  data_points: number;
  calculation_method: string;
}

interface ActivityAnalyticsProps {
  activityId: number;
}

function AnalyticsCard({ children }: { children: ReactNode }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
      {children}
    </section>
  );
}

function StatusBadge({
  children,
  tone,
}: {
  children: ReactNode;
  tone: "neutral" | "good" | "warn" | "bad";
}) {
  return (
    <span
      className={cn(
        "rounded-md px-2 py-0.5 text-[11px] font-medium",
        tone === "good" && "bg-emerald-50 text-emerald-800",
        tone === "warn" && "bg-amber-50 text-amber-800",
        tone === "bad" && "bg-red-50 text-red-800",
        tone === "neutral" && "bg-slate-100 text-slate-700",
      )}
    >
      {children}
    </span>
  );
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex justify-between gap-3 text-sm">
      <span className="text-slate-500">{label}</span>
      <span className="tabular-nums text-slate-800">{value}</span>
    </div>
  );
}

const ActivityAnalytics = ({ activityId }: ActivityAnalyticsProps) => {
  const [negativeSplit, setNegativeSplit] = useState<MetricState<NegativeSplitData>>(
    initialMetricState<NegativeSplitData>(),
  );
  const [decoupling, setDecoupling] = useState<MetricState<DecouplingData>>(
    initialMetricState<DecouplingData>(),
  );

  useEffect(() => {
    let cancelled = false;

    const loadMetric = async <T,>(
      fetcher: () => Promise<T>,
      setter: (state: MetricState<T>) => void,
    ) => {
      setter({ status: "loading", data: null, error: null });
      try {
        const data = await fetcher();
        if (!cancelled) setter({ status: "ready", data, error: null });
      } catch (error) {
        if (cancelled) return;
        if (classifyApiError(error) === "not_found") {
          setter({ status: "missing", data: null, error: null });
          return;
        }
        setter({
          status: "error",
          data: null,
          error: apiErrorMessage(error),
        });
      }
    };

    void Promise.all([
      loadMetric(
        () => analysisApi.getNegativeSplit(activityId) as Promise<NegativeSplitData>,
        setNegativeSplit,
      ),
      loadMetric(
        () => analysisApi.getDecoupling(activityId) as Promise<DecouplingData>,
        setDecoupling,
      ),
    ]);

    return () => {
      cancelled = true;
    };
  }, [activityId]);

  const formatPace = (pace: number | null | undefined) => {
    if (pace === null || pace === undefined || Number.isNaN(pace)) return "—";
    const minutes = Math.floor(pace);
    const seconds = Math.round((pace - minutes) * 60);
    return `${minutes}:${seconds.toString().padStart(2, "0")}`;
  };

  const negativeSplitBadge = (value: number | null | undefined) => {
    if (value == null || Number.isNaN(value)) {
      return <StatusBadge tone="neutral">Ingen data</StatusBadge>;
    }
    if (value < 0) return <StatusBadge tone="good">Negativ split</StatusBadge>;
    if (value > 0) return <StatusBadge tone="bad">Positiv split</StatusBadge>;
    return <StatusBadge tone="neutral">Jevn split</StatusBadge>;
  };

  const decouplingBadge = (value: number | null | undefined) => {
    if (value == null || Number.isNaN(value)) {
      return <StatusBadge tone="neutral">Ingen data</StatusBadge>;
    }
    if (value > 10) return <StatusBadge tone="bad">Høy decoupling</StatusBadge>;
    if (value >= 5) return <StatusBadge tone="warn">Moderat decoupling</StatusBadge>;
    return <StatusBadge tone="good">Lav decoupling</StatusBadge>;
  };

  const isLoading =
    negativeSplit.status === "loading" || decoupling.status === "loading";
  const hasApiErrors =
    negativeSplit.status === "error" || decoupling.status === "error";
  const hasAnyData =
    negativeSplit.status === "ready" || decoupling.status === "ready";

  if (isLoading && !hasAnyData) {
    return (
      <AnalyticsCard>
        <h3 className="text-sm font-semibold text-slate-900">Løpsanalyse</h3>
        <p className="mt-1 text-sm text-slate-500">Laster analysedata...</p>
      </AnalyticsCard>
    );
  }

  if (hasApiErrors && !hasAnyData) {
    return (
      <AnalyticsCard>
        <h3 className="text-sm font-semibold text-slate-900">Løpsanalyse</h3>
        <p className="mt-1 text-sm text-red-700">Kunne ikke laste analysedata.</p>
      </AnalyticsCard>
    );
  }

  if (!hasAnyData && !hasApiErrors) {
    return (
      <AnalyticsCard>
        <h3 className="text-sm font-semibold text-slate-900">Løpsanalyse</h3>
        <p className="mt-1 text-sm text-slate-500">
          Ingen analysedata tilgjengelig for denne aktiviteten.
        </p>
      </AnalyticsCard>
    );
  }

  return (
    <div className="space-y-4">
      {hasApiErrors ? (
        <AnalyticsCard>
          <p className="text-sm text-amber-800">
            Noen analysedata kunne ikke hentes.
            {negativeSplit.error ? ` Negativ split: ${negativeSplit.error}.` : ""}
            {decoupling.error ? ` Decoupling: ${decoupling.error}.` : ""}
          </p>
        </AnalyticsCard>
      ) : null}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {negativeSplit.status === "ready" && negativeSplit.data ? (
          <AnalyticsCard>
            <div className="flex items-start justify-between gap-2">
              <h3 className="text-sm font-semibold text-slate-900">Negativ split</h3>
              {negativeSplitBadge(negativeSplit.data.negative_split_percent)}
            </div>
            <p className="mt-3 text-2xl font-semibold tabular-nums text-slate-900">
              {negativeSplit.data.negative_split_percent > 0 ? "+" : ""}
              {negativeSplit.data.negative_split_percent?.toFixed(1) || "0.0"}%
            </p>
            <div className="mt-3 space-y-1.5">
              <Row
                label="Første halvdel"
                value={`${formatPace(negativeSplit.data.first_half_pace)} /km`}
              />
              <Row
                label="Andre halvdel"
                value={`${formatPace(negativeSplit.data.second_half_pace)} /km`}
              />
              <Row
                label="Datapunkter"
                value={negativeSplit.data.data_points?.toLocaleString("nb-NO") || "—"}
              />
              <Row
                label="Kilde"
                value={
                  negativeSplit.data.calculation_method === "cached" ? "Cache" : "FIT-data"
                }
              />
            </div>
            <p className="mt-3 text-xs text-slate-500">
              {negativeSplit.data.negative_split_percent < 0
                ? "Raskere i andre halvdel — god pacing."
                : negativeSplit.data.negative_split_percent > 0
                  ? "Saktere i andre halvdel — vurder pacing-strategi."
                  : "Ikke nok data for pacing-analyse."}
            </p>
          </AnalyticsCard>
        ) : null}

        {decoupling.status === "ready" && decoupling.data ? (
          <AnalyticsCard>
            <div className="flex items-start justify-between gap-2">
              <h3 className="text-sm font-semibold text-slate-900">
                Cardiac-aerobic decoupling
              </h3>
              {decouplingBadge(decoupling.data.decoupling_percent)}
            </div>
            <p className="mt-3 text-2xl font-semibold tabular-nums text-slate-900">
              {decoupling.data.decoupling_percent > 0 ? "+" : ""}
              {decoupling.data.decoupling_percent?.toFixed(1) || "0.0"}%
            </p>
            <div className="mt-3 space-y-1.5">
              <Row
                label="Første halvdel"
                value={`HR ${decoupling.data.first_half_hr?.toFixed(0) || "—"} / ${decoupling.data.first_half_speed?.toFixed(2) || "—"} m/s`}
              />
              <Row
                label="Andre halvdel"
                value={`HR ${decoupling.data.second_half_hr?.toFixed(0) || "—"} / ${decoupling.data.second_half_speed?.toFixed(2) || "—"} m/s`}
              />
              <Row
                label="HR:fart 1. del"
                value={decoupling.data.first_half_ratio?.toFixed(2) || "—"}
              />
              <Row
                label="HR:fart 2. del"
                value={decoupling.data.second_half_ratio?.toFixed(2) || "—"}
              />
              <Row
                label="Datapunkter"
                value={decoupling.data.data_points?.toLocaleString("nb-NO") || "—"}
              />
            </div>
            <p className="mt-3 text-xs text-slate-500">
              {decoupling.data.decoupling_percent > 10
                ? "Høy decoupling kan indikere tretthet eller dehydrering."
                : decoupling.data.decoupling_percent >= 5
                  ? "Moderat decoupling — vær oppmerksom på tretthet."
                  : decoupling.data.decoupling_percent < 5
                    ? "Lav decoupling — god aerob effektivitet."
                    : "Ikke nok data for decoupling-analyse."}
            </p>
          </AnalyticsCard>
        ) : null}
      </div>
    </div>
  );
};

export default ActivityAnalytics;
