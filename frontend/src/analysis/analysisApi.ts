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

export type AnalysisRangeOpts = {
  endDate?: string;
  startDate?: string;
};

function withRange(base: string, opts?: AnalysisRangeOpts): string {
  const url = new URL(base, "http://local");
  if (opts?.endDate) url.searchParams.set("end_date", opts.endDate);
  if (opts?.startDate) url.searchParams.set("start_date", opts.startDate);
  return `${url.pathname}${url.search}`;
}

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
  development: (period: string, multiHorizon = false, range?: AnalysisRangeOpts) =>
    getJson<DevelopmentPayload>(
      withRange(
        `/api/analysis/development?period=${encodeURIComponent(period)}&multi_horizon=${multiHorizon ? "true" : "false"}`,
        range,
      ),
    ),
  timeseries: (period: string, metrics: string[], range?: AnalysisRangeOpts) =>
    getJson<TimeseriesPayload>(
      withRange(
        `/api/analysis/timeseries?period=${encodeURIComponent(period)}&metrics=${encodeURIComponent(metrics.join(","))}`,
        range,
      ),
    ),
  relationships: (period: string, range?: AnalysisRangeOpts) =>
    getJson<RelationshipsPayload>(
      withRange(`/api/analysis/relationships?period=${encodeURIComponent(period)}`, range),
    ),
  relationshipMatrix: (period: string, advanced = false, range?: AnalysisRangeOpts) =>
    getJson<RelationshipMatrixPayload>(
      withRange(
        `/api/analysis/relationship-matrix?period=${encodeURIComponent(period)}&advanced=${advanced ? "true" : "false"}`,
        range,
      ),
    ),
  trainingResponse: (period: string, outcome: string, range?: AnalysisRangeOpts) =>
    getJson<TrainingResponsePayload>(
      withRange(
        `/api/analysis/training-response?period=${encodeURIComponent(period)}&outcome=${encodeURIComponent(outcome)}`,
        range,
      ),
    ),
  intensityDistribution: (period: string, range?: AnalysisRangeOpts) =>
    getJson<IntensityDistributionPayload>(
      withRange(
        `/api/analysis/intensity-distribution?period=${encodeURIComponent(period)}`,
        range,
      ),
    ),
  durationCurveHistory: (period: string, range?: AnalysisRangeOpts) =>
    getJson<DurationCurvePayload>(
      withRange(
        `/api/analysis/duration-curve-history?period=${encodeURIComponent(period)}`,
        range,
      ),
    ),
  bestPeriodBacktrace: (period: string, metric: string, range?: AnalysisRangeOpts) =>
    getJson<BestPeriodBacktracePayload>(
      withRange(
        `/api/analysis/best-period-backtrace?period=${encodeURIComponent(period)}&metric=${encodeURIComponent(metric)}`,
        range,
      ),
    ),
  history: (period: string) =>
    getJson<HistoryPayload>(`/api/analysis/history?period=${encodeURIComponent(period)}`),
  periodComparison: (period: string, range?: AnalysisRangeOpts) =>
    getJson<PeriodComparisonPayload>(
      withRange(`/api/analysis/period-comparison?period=${encodeURIComponent(period)}`, range),
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
