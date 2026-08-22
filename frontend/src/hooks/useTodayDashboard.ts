"use client";

import { useQuery } from "@tanstack/react-query";
import { todayApi } from "@/dashboard/todayApi";
import { COCKPIT_QUERY_DEFAULTS } from "@/lib/cockpitQueryDefaults";

export const todayKeys = {
  all: ["today"] as const,
  dashboard: (date?: string) => [...todayKeys.all, "dashboard", date || "today"] as const,
};

export function useTodayDashboard(date?: string, enabled = true) {
  return useQuery({
    queryKey: todayKeys.dashboard(date),
    queryFn: () => todayApi.today(date),
    enabled,
    ...COCKPIT_QUERY_DEFAULTS,
  });
}
