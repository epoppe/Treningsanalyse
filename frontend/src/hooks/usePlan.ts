"use client";

import { useQuery } from "@tanstack/react-query";
import { planApi } from "@/dashboard/planApi";

export const planKeys = {
  all: ["plan"] as const,
  dashboard: (date?: string) => [...planKeys.all, "dashboard", date || "today"] as const,
};

export function usePlan(date?: string) {
  return useQuery({
    queryKey: planKeys.dashboard(date),
    queryFn: () => planApi.plan(date),
    staleTime: 60_000,
    retry: 1,
  });
}
