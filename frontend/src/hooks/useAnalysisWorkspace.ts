"use client";

import { useQuery } from "@tanstack/react-query";
import { analysisApi } from "@/analysis/analysisApi";

export function useAnalysisCatalog() {
  return useQuery({
    queryKey: ["analysis", "catalog"],
    queryFn: () => analysisApi.catalog(),
    staleTime: 300_000,
    retry: 1,
  });
}

export function useDevelopment(period: string, multiHorizon = true) {
  return useQuery({
    queryKey: ["analysis", "development", period, multiHorizon],
    queryFn: () => analysisApi.development(period, multiHorizon),
    staleTime: 60_000,
    retry: 1,
  });
}

export function useTimeseries(period: string, metrics: string[]) {
  return useQuery({
    queryKey: ["analysis", "timeseries", period, metrics.join(",")],
    queryFn: () => analysisApi.timeseries(period, metrics),
    enabled: metrics.length > 0,
    staleTime: 60_000,
    retry: 1,
  });
}

export function useRelationships(period: string) {
  return useQuery({
    queryKey: ["analysis", "relationships", period],
    queryFn: () => analysisApi.relationships(period),
    staleTime: 60_000,
    retry: 1,
  });
}

export function useRelationshipMatrix(period: string, advanced = false, enabled = true) {
  return useQuery({
    queryKey: ["analysis", "relationship-matrix", period, advanced],
    queryFn: () => analysisApi.relationshipMatrix(period, advanced),
    enabled,
    staleTime: 60_000,
    retry: 1,
  });
}

export function useTrainingResponse(period: string, outcome: string, enabled = true) {
  return useQuery({
    queryKey: ["analysis", "training-response", period, outcome],
    queryFn: () => analysisApi.trainingResponse(period, outcome),
    enabled: enabled && Boolean(outcome),
    staleTime: 60_000,
    retry: 1,
  });
}

export function useIntensityDistribution(period: string, enabled = true) {
  return useQuery({
    queryKey: ["analysis", "intensity-distribution", period],
    queryFn: () => analysisApi.intensityDistribution(period),
    enabled,
    staleTime: 60_000,
    retry: 1,
  });
}

export function useDurationCurveHistory(period: string, enabled = true) {
  return useQuery({
    queryKey: ["analysis", "duration-curve", period],
    queryFn: () => analysisApi.durationCurveHistory(period),
    enabled,
    staleTime: 60_000,
    retry: 1,
  });
}

export function useBestPeriodBacktrace(period: string, metric: string, enabled = true) {
  return useQuery({
    queryKey: ["analysis", "best-period", period, metric],
    queryFn: () => analysisApi.bestPeriodBacktrace(period, metric),
    enabled: enabled && Boolean(metric),
    staleTime: 60_000,
    retry: 1,
  });
}

export function useHistory(period: string) {
  return useQuery({
    queryKey: ["analysis", "history", period],
    queryFn: () => analysisApi.history(period),
    staleTime: 60_000,
    retry: 1,
  });
}

export function usePeriodComparison(period: string, enabled = true) {
  return useQuery({
    queryKey: ["analysis", "period-comparison", period],
    queryFn: () => analysisApi.periodComparison(period),
    enabled,
    staleTime: 60_000,
    retry: 1,
  });
}

export function useWeekExplorer(weekDate?: string) {
  return useQuery({
    queryKey: ["analysis", "week", weekDate],
    queryFn: () => analysisApi.week(weekDate!),
    enabled: Boolean(weekDate),
    staleTime: 60_000,
    retry: 1,
  });
}

export function useHighlights(period = "1y") {
  return useQuery({
    queryKey: ["analysis", "highlights", period],
    queryFn: () => analysisApi.highlights(period),
    staleTime: 120_000,
    retry: 1,
  });
}

export function useRelationshipLag(
  stimulus?: string,
  outcome?: string,
  period = "1y",
  enabled = true,
) {
  return useQuery({
    queryKey: ["analysis", "relationship-lag", stimulus, outcome, period],
    queryFn: () => analysisApi.relationshipLag(stimulus!, outcome!, period),
    enabled: enabled && Boolean(stimulus && outcome),
    staleTime: 60_000,
    retry: 1,
  });
}

export function useHistoryYoy(months = 12, enabled = true) {
  return useQuery({
    queryKey: ["analysis", "history-yoy", months],
    queryFn: () => analysisApi.historyYoy(months),
    enabled,
    staleTime: 120_000,
    retry: 1,
  });
}

export function useHistoryPerformanceRecovery(months = 12, enabled = true) {
  return useQuery({
    queryKey: ["analysis", "history-performance", months],
    queryFn: () => analysisApi.historyPerformanceRecovery(months),
    enabled,
    staleTime: 120_000,
    retry: 1,
  });
}

export function useHistoryAnnotations(limit = 24, enabled = true) {
  return useQuery({
    queryKey: ["analysis", "history-annotations", limit],
    queryFn: () => analysisApi.historyAnnotations(limit),
    enabled,
    staleTime: 120_000,
    retry: 1,
  });
}
