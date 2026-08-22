import type { TodayDashboardPayload } from "@/types/today";
import type {
  ComparableSessionsPayload,
  HistoricalSupportPayload,
  PostSyncSummaryPayload,
  RecommendationHistoryPayload,
  WhatChangedPayload,
} from "@/types/dashboard";

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const todayApi = {
  today: (date?: string, persist = false) => {
    const params = new URLSearchParams();
    if (date) params.set("target_date", date);
    if (persist) params.set("persist", "true");
    const q = params.toString();
    return getJson<TodayDashboardPayload>(`/api/dashboard/today${q ? `?${q}` : ""}`);
  },
  whatChanged: (refresh = true) =>
    getJson<WhatChangedPayload>(
      `/api/dashboard/what-changed?refresh=${refresh ? "true" : "false"}`,
    ),
  postSyncSummary: (activityId: string) =>
    getJson<PostSyncSummaryPayload>(
      `/api/dashboard/post-sync-summary?activity_id=${encodeURIComponent(activityId)}`,
    ),
  recommendationHistory: (limit = 30) =>
    getJson<RecommendationHistoryPayload>(`/api/dashboard/recommendation-history?limit=${limit}`),
  decisionHistoricalSupport: (workoutType?: string, date?: string) => {
    const params = new URLSearchParams();
    if (workoutType) params.set("workout_type", workoutType);
    if (date) params.set("target_date", date);
    const q = params.toString();
    return getJson<HistoricalSupportPayload>(
      `/api/dashboard/decision-historical-support${q ? `?${q}` : ""}`,
    );
  },
  comparableSessions: (activityId: string) =>
    getJson<ComparableSessionsPayload>(
      `/api/dashboard/comparable-sessions?activity_id=${encodeURIComponent(activityId)}`,
    ),
};
