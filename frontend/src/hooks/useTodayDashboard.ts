"use client";

import { useQuery } from "@tanstack/react-query";
import { todayApi } from "@/dashboard/todayApi";

export const todayKeys = {
  all: ["today"] as const,
  dashboard: (date?: string) => [...todayKeys.all, "dashboard", date || "today"] as const,
};

export function useTodayDashboard(date?: string) {
  return useQuery({
    queryKey: todayKeys.dashboard(date),
    queryFn: () => todayApi.today(date),
    staleTime: 60_000,
    retry: 1,
  });
}
