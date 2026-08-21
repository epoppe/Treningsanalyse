"use client";

import { useQuery } from "@tanstack/react-query";
import { analysisApi } from "@/analysis/analysisApi";

export function useDevelopment(period: string) {
  return useQuery({
    queryKey: ["analysis", "development", period],
    queryFn: () => analysisApi.development(period),
    staleTime: 60_000,
  });
}

export function useTimeseries(period: string, metrics: string[]) {
  return useQuery({
    queryKey: ["analysis", "timeseries", period, metrics.join(",")],
    queryFn: () => analysisApi.timeseries(period, metrics),
    enabled: metrics.length > 0,
    staleTime: 60_000,
  });
}

export function useRelationships(period: string) {
  return useQuery({
    queryKey: ["analysis", "relationships", period],
    queryFn: () => analysisApi.relationships(period),
    staleTime: 60_000,
  });
}

export function useHistory(period: string) {
  return useQuery({
    queryKey: ["analysis", "history", period],
    queryFn: () => analysisApi.history(period),
    staleTime: 60_000,
  });
}

export function usePeriodComparison(period: string) {
  return useQuery({
    queryKey: ["analysis", "period-comparison", period],
    queryFn: () => analysisApi.periodComparison(period),
    staleTime: 60_000,
  });
}
