import type {
  DevelopmentPayload,
  HistoryPayload,
  PeriodComparisonPayload,
  RelationshipsPayload,
  TimeseriesPayload,
} from "@/types/analysis";

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const analysisApi = {
  development: (period: string) =>
    getJson<DevelopmentPayload>(`/api/analysis/development?period=${encodeURIComponent(period)}`),
  timeseries: (period: string, metrics: string[]) =>
    getJson<TimeseriesPayload>(
      `/api/analysis/timeseries?period=${encodeURIComponent(period)}&metrics=${encodeURIComponent(metrics.join(","))}`
    ),
  relationships: (period: string) =>
    getJson<RelationshipsPayload>(
      `/api/analysis/relationships?period=${encodeURIComponent(period)}`
    ),
  history: (period: string) =>
    getJson<HistoryPayload>(`/api/analysis/history?period=${encodeURIComponent(period)}`),
  periodComparison: (period: string) =>
    getJson<PeriodComparisonPayload>(
      `/api/analysis/period-comparison?period=${encodeURIComponent(period)}`
    ),
};
