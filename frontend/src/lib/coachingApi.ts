import axios from "axios";
import type {
  InsightsSummary,
  PlanSummary,
  ProgressSummary,
  SystemHealthPayload,
  TodayDashboard,
} from "@/types/coaching";

const client = axios.create({
  baseURL: "/api",
  timeout: 60000,
});

export const coachingApi = {
  async getToday(targetDate?: string): Promise<TodayDashboard> {
    const { data } = await client.get<TodayDashboard>("/coaching/today", {
      params: targetDate ? { target_date: targetDate } : undefined,
    });
    return data;
  },
  async getPlan(targetDate?: string): Promise<PlanSummary> {
    const { data } = await client.get<PlanSummary>("/coaching/plan", {
      params: targetDate ? { target_date: targetDate } : undefined,
    });
    return data;
  },
  async getProgress(targetDate?: string): Promise<ProgressSummary> {
    const { data } = await client.get<ProgressSummary>("/coaching/progress-summary", {
      params: targetDate ? { target_date: targetDate } : undefined,
    });
    return data;
  },
  async getInsights(targetDate?: string): Promise<InsightsSummary> {
    const { data } = await client.get<InsightsSummary>("/coaching/insights-summary", {
      params: targetDate ? { target_date: targetDate } : undefined,
    });
    return data;
  },
  async getSystemHealth(targetDate?: string): Promise<SystemHealthPayload> {
    const { data } = await client.get<SystemHealthPayload>("/coaching/system-health", {
      params: targetDate ? { target_date: targetDate } : undefined,
    });
    return data;
  },
};
