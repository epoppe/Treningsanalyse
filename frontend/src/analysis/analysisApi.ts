import type {
  AnalysisCatalogPayload,
  BestPeriodBacktracePayload,
  DevelopmentPayload,
  DurationCurvePayload,
  HistoryPayload,
  IntensityDistributionPayload,
  PeriodComparisonPayload,
  RelationshipLagPayload,
  RelationshipMatrixPayload,
  RelationshipsPayload,
  HighlightsPayload,
  HistoryAnnotationsPayload,
  TimeseriesPayload,
  TrainingResponsePayload,
  WeekExplorerPayload,
  YoYPayload,
  PerformanceRecoveryPayload,
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
  catalog: () => getJson<AnalysisCatalogPayload>(`/api/analysis/catalog`),
  development: (period: string, multiHorizon = false) =>
    getJson<DevelopmentPayload>(
      `/api/analysis/development?period=${encodeURIComponent(period)}&multi_horizon=${multiHorizon ? "true" : "false"}`,
    ),
  timeseries: (period: string, metrics: string[]) =>
    getJson<TimeseriesPayload>(
      `/api/analysis/timeseries?period=${encodeURIComponent(period)}&metrics=${encodeURIComponent(metrics.join(","))}`
    ),
  relationships: (period: string) =>
    getJson<RelationshipsPayload>(
      `/api/analysis/relationships?period=${encodeURIComponent(period)}`
    ),
  relationshipMatrix: (period: string, advanced = false) =>
    getJson<RelationshipMatrixPayload>(
      `/api/analysis/relationship-matrix?period=${encodeURIComponent(period)}&advanced=${advanced ? "true" : "false"}`
    ),
  trainingResponse: (period: string, outcome: string) =>
    getJson<TrainingResponsePayload>(
      `/api/analysis/training-response?period=${encodeURIComponent(period)}&outcome=${encodeURIComponent(outcome)}`
    ),
  intensityDistribution: (period: string) =>
    getJson<IntensityDistributionPayload>(
      `/api/analysis/intensity-distribution?period=${encodeURIComponent(period)}`
    ),
  durationCurveHistory: (period: string) =>
    getJson<DurationCurvePayload>(
      `/api/analysis/duration-curve-history?period=${encodeURIComponent(period)}`
    ),
  bestPeriodBacktrace: (period: string, metric: string) =>
    getJson<BestPeriodBacktracePayload>(
      `/api/analysis/best-period-backtrace?period=${encodeURIComponent(period)}&metric=${encodeURIComponent(metric)}`
    ),
  history: (period: string) =>
    getJson<HistoryPayload>(`/api/analysis/history?period=${encodeURIComponent(period)}`),
  periodComparison: (period: string) =>
    getJson<PeriodComparisonPayload>(
      `/api/analysis/period-comparison?period=${encodeURIComponent(period)}`
    ),
  week: (weekDate: string) =>
    getJson<WeekExplorerPayload>(`/api/analysis/week/${encodeURIComponent(weekDate)}`),
  highlights: (period = "1y") =>
    getJson<HighlightsPayload>(`/api/analysis/highlights?period=${encodeURIComponent(period)}`),
  relationshipLag: (stimulus: string, outcome: string, period: string) =>
    getJson<RelationshipLagPayload>(
      `/api/analysis/relationship-lag?stimulus=${encodeURIComponent(stimulus)}&outcome=${encodeURIComponent(outcome)}&period=${encodeURIComponent(period)}`,
    ),
  historyYoy: (months = 12) =>
    getJson<YoYPayload>(`/api/analysis/history/yoy?months=${months}`),
  historyPerformanceRecovery: (months = 12) =>
    getJson<PerformanceRecoveryPayload>(
      `/api/analysis/history/performance-recovery?months=${months}`,
    ),
  historyAnnotations: (limit = 24) =>
    getJson<HistoryAnnotationsPayload>(`/api/analysis/history/annotations?limit=${limit}`),
  dependencyCheck: (x: string, y: string, advanced = false) =>
    getJson<{
      x: string;
      y: string;
      relationship_kind: string;
      relationship_type: string;
      suppress_default: boolean;
      warning?: string | null;
      allow_advanced?: boolean;
    }>(
      `/api/analysis/dependency-check?x=${encodeURIComponent(x)}&y=${encodeURIComponent(y)}&advanced=${advanced ? "true" : "false"}`
    ),
};
