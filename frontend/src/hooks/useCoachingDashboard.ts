"use client";

import { useQuery } from "@tanstack/react-query";
import { coachingApi } from "@/lib/coachingApi";

export function useTodayDashboard(targetDate?: string) {
  return useQuery({
    queryKey: ["coaching", "today", targetDate ?? "today"],
    queryFn: () => coachingApi.getToday(targetDate),
    staleTime: 60_000,
  });
}

export function usePlanSummary(targetDate?: string) {
  return useQuery({
    queryKey: ["coaching", "plan", targetDate ?? "today"],
    queryFn: () => coachingApi.getPlan(targetDate),
    staleTime: 60_000,
  });
}

export function useProgressSummary(targetDate?: string) {
  return useQuery({
    queryKey: ["coaching", "progress", targetDate ?? "today"],
    queryFn: () => coachingApi.getProgress(targetDate),
    staleTime: 60_000,
  });
}

export function useInsightsSummary(targetDate?: string) {
  return useQuery({
    queryKey: ["coaching", "insights", targetDate ?? "today"],
    queryFn: () => coachingApi.getInsights(targetDate),
    staleTime: 60_000,
  });
}

export function useSystemHealth(targetDate?: string) {
  return useQuery({
    queryKey: ["coaching", "system", targetDate ?? "today"],
    queryFn: () => coachingApi.getSystemHealth(targetDate),
    staleTime: 60_000,
  });
}
