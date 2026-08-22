"use client";

import { useQuery } from "@tanstack/react-query";
import { todayApi } from "@/dashboard/todayApi";
import { COCKPIT_DELTA_STALE_MS, COCKPIT_QUERY_DEFAULTS } from "@/lib/cockpitQueryDefaults";

export const whatChangedKeys = {
  all: ["what-changed"] as const,
  latest: (refresh: boolean) => [...whatChangedKeys.all, refresh] as const,
};

export function useWhatChanged(refresh = false, enabled = true) {
  return useQuery({
    queryKey: whatChangedKeys.latest(refresh),
    queryFn: () => todayApi.whatChanged(refresh),
    enabled,
    staleTime: COCKPIT_DELTA_STALE_MS,
    retry: COCKPIT_QUERY_DEFAULTS.retry,
    refetchOnWindowFocus: COCKPIT_QUERY_DEFAULTS.refetchOnWindowFocus,
  });
}

export const postSyncKeys = {
  all: ["post-sync"] as const,
  activity: (id: string) => [...postSyncKeys.all, id] as const,
};

export function usePostSyncSummary(activityId?: string) {
  return useQuery({
    queryKey: postSyncKeys.activity(activityId || ""),
    queryFn: () => todayApi.postSyncSummary(activityId!),
    enabled: Boolean(activityId),
    ...COCKPIT_QUERY_DEFAULTS,
  });
}

export const recommendationHistoryKeys = {
  all: ["recommendation-history"] as const,
  list: (limit: number) => [...recommendationHistoryKeys.all, limit] as const,
};

export function useRecommendationHistory(limit = 30) {
  return useQuery({
    queryKey: recommendationHistoryKeys.list(limit),
    queryFn: () => todayApi.recommendationHistory(limit),
    ...COCKPIT_QUERY_DEFAULTS,
  });
}

export const historicalSupportKeys = {
  all: ["decision-historical-support"] as const,
  detail: (workoutType?: string, date?: string) =>
    [...historicalSupportKeys.all, workoutType || "auto", date || "today"] as const,
};

export function useDecisionHistoricalSupport(workoutType?: string, date?: string, enabled = true) {
  return useQuery({
    queryKey: historicalSupportKeys.detail(workoutType, date),
    queryFn: () => todayApi.decisionHistoricalSupport(workoutType, date),
    enabled,
    ...COCKPIT_QUERY_DEFAULTS,
  });
}

export const comparableSessionsKeys = {
  all: ["comparable-sessions"] as const,
  activity: (id: string) => [...comparableSessionsKeys.all, id] as const,
};

export function useComparableSessions(activityId?: string) {
  return useQuery({
    queryKey: comparableSessionsKeys.activity(activityId || ""),
    queryFn: () => todayApi.comparableSessions(activityId!),
    enabled: Boolean(activityId),
    ...COCKPIT_QUERY_DEFAULTS,
  });
}
