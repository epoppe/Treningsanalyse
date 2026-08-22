/** Analysis workspace TypeScript contracts. */

export type AnalysisPeriod = "28d" | "90d" | "6m" | "1y" | "2y" | "all";
export type AnalysisSport = "running" | "cycling" | "all";
export type AnalysisSession =
  | "all"
  | "easy"
  | "long"
  | "threshold"
  | "vo2"
  | "race";
export type AnalysisTab = "utvikling" | "sammenhenger" | "historikk";

export type EvidenceBand = "strong" | "supported" | "emerging" | "insufficient";
export type TrendDirection = "improving" | "stable" | "declining" | "uncertain" | string;

export type RelationshipType =
  | "SAME_TIME_ASSOCIATION"
  | "LAGGED_ASSOCIATION"
  | "TRAINING_RESPONSE"
  | "MATHEMATICAL_DEPENDENCY"
  | "PROSPECTIVE_EVIDENCE";

export interface AnalyticsMetric {
  key: string;
  label: string;
  analytic_role?: string;
  category?: string;
  scope?: string;
  unit?: string;
  direction?: string;
  selectable_x?: boolean;
  selectable_y?: boolean;
  supports_lag?: boolean;
  supports_trend?: boolean;
  supports_period_comparison?: boolean;
  minimum_samples?: number;
  source_type?: string;
  dependencies?: string[];
  recommended_lags_days?: number[];
  group?: string;
  explanation?: string;
  expose_default?: boolean;
  aggregation_days?: number;
  stimulus_kind?: string;
}

export interface AnalysisPreset {
  id: string;
  title: string;
  outcome: string;
  predictors: string[];
  lags?: number[];
  mode?: RelationshipType | string;
}

export interface AnalysisCatalogPayload {
  metrics: AnalyticsMetric[];
  groups: Record<string, string[]>;
  presets: AnalysisPreset[];
  matrix: { predictors: string[]; outcomes: string[] };
  lag_families: Record<string, number[]>;
  relationship_types: string[];
  disclaimer?: string;
}

export interface DevelopmentDomain {
  domain: string;
  metric: string;
  label: string;
  direction?: TrendDirection;
  direction_label?: string;
  relative_change_pct?: number | null;
  absolute_change?: number | null;
  current?: number | null;
  baseline?: number | null;
  sample_count: number;
  confidence?: number | null;
  evidence: EvidenceBand | string;
  change_point_detected?: boolean;
  window?: string;
  horizons?: Record<string, DevelopmentDomain>;
}

export interface DevelopmentPayload {
  date: string;
  period: string;
  period_days: number;
  window: string;
  domains: DevelopmentDomain[];
  available_metrics?: string[];
  disclaimer?: string;
}

export interface TimeseriesPoint {
  date: string;
  value: number;
}

export interface TimeseriesPayload {
  start_date: string;
  end_date: string;
  period: string;
  series: Record<
    string,
    {
      metric: string;
      label?: string;
      points: TimeseriesPoint[];
      sample_count: number;
      missing_days_approx?: number;
      unit_note?: string;
      scope?: string;
      unit?: string;
      alignment?: string;
      note?: string;
    }
  >;
  note?: string;
}

export interface RelationshipCardData {
  id: string;
  question: string;
  stimulus: string;
  outcome: string;
  section: string;
  status: string;
  association: string;
  strength: string;
  relationship_type?: RelationshipType | string;
  lag_days?: number | null;
  sample_count: number;
  evidence: string;
  effect?: number | null;
  wording: string;
}

export interface RelationshipsPayload {
  date: string;
  period: string;
  cards: RelationshipCardData[];
  sections: string[];
  advanced_scatter?: string;
  disclaimer?: string;
  ranking_eligible_count?: number;
}

export interface MatrixCell {
  predictor: string;
  outcome: string;
  status: string;
  relationship_type?: string;
  association?: string;
  effect?: number | null;
  lag_days?: number | null;
  sample_count?: number;
  evidence?: string;
  warning?: string | null;
  note?: string;
}

export interface RelationshipMatrixPayload {
  date: string;
  period: string;
  predictors: string[];
  outcomes: string[];
  cells: MatrixCell[];
  disclaimer?: string;
}

export interface TrainingResponsePayload {
  date: string;
  period: string;
  outcome: string;
  mode: string;
  suggested_predictors: string[];
  relationships: Array<{
    stimulus?: string;
    outcome?: string;
    association?: string;
    lag_days?: number | null;
    effect_size?: number | null;
    sample_count?: number;
    evidence?: string;
    relationship_type?: string;
    wording?: string;
  }>;
  disclaimer?: string;
  multiple_testing?: Record<string, unknown>;
}

export interface DurationCurvePayload {
  start_date: string;
  end_date: string;
  period: string;
  curves: Array<{
    metric: string;
    duration_label: string;
    current?: number | null;
    previous_year?: number | null;
    rolling_best?: number | null;
    sample_count: number;
    points: TimeseriesPoint[];
  }>;
  disclaimer?: string;
}

export interface BestPeriodBacktracePayload {
  metric: string;
  status: string;
  period?: string;
  best_periods: Array<{
    peak_date: string;
    peak_value: number;
    wording?: string;
    preceding_blocks: Array<{
      weeks: number;
      status: string;
      sample_weeks: number;
      total_duration_seconds?: number;
      total_tss?: number;
      total_distance_meters?: number;
      activity_count?: number;
      avg_weekly_duration_seconds?: number;
    }>;
  }>;
  note?: string;
  disclaimer?: string;
}

export interface IntensityDistributionPayload {
  start_date: string;
  end_date: string;
  period: string;
  requested_windows_days: number[];
  series: TimeseriesPayload["series"];
  note?: string;
}

export interface HistoryMonth {
  month_start?: string | null;
  month_end?: string | null;
  year?: number;
  month?: number;
  total_duration_seconds?: number | null;
  total_distance_meters?: number | null;
  activity_count?: number | null;
  total_tss?: number | null;
}

export interface HistoryPayload {
  start_date: string;
  end_date: string;
  period: string;
  years: Array<{ year: string; months: HistoryMonth[] }>;
  month_count: number;
  note?: string;
}

export interface PeriodComparisonRow {
  metric: string;
  period_a: { label: string; end: string; value?: number | null; sample_count: number };
  period_b: { label: string; end: string; value?: number | null; sample_count: number };
  difference?: number | null;
  evidence: string;
  explanation?: string;
}

export interface PeriodComparisonPayload {
  period: string;
  days: number;
  rows: PeriodComparisonRow[];
  disclaimer?: string;
}

export interface AnalysisFilters {
  tab: AnalysisTab;
  period: AnalysisPeriod;
  sport: AnalysisSport;
  session: AnalysisSession;
  metrics: string[];
  outcome?: string;
  preset?: string;
  backtrace?: string;
  week?: string;
}

export interface WeekExplorerPayload {
  week_start: string;
  week_end: string;
  summary?: {
    total_duration?: number | null;
    total_distance?: number | null;
    activity_count?: number | null;
  } | null;
  sessions: Array<{
    activity_id?: string;
    name?: string;
    type?: string;
    date?: string;
    distance_m?: number;
    duration_s?: number;
  }>;
  compare_links?: { previous_week?: string };
}

export interface HighlightsPayload {
  date: string;
  period: string;
  highlights: Array<{
    type?: string;
    metric?: string;
    direction?: string;
    relative_change_pct?: number | null;
    evidence?: string;
    summary?: string;
  }>;
  disclaimer?: string;
}

export interface RelationshipLagPayload {
  date: string;
  period: string;
  stimulus: string;
  outcome: string;
  profile: Array<{
    lag_days: number;
    effect_size?: number | null;
    relationship?: string;
    sample_count?: number;
    evidence?: string;
  }>;
  best_lag_days?: number | null;
  disclaimer?: string;
}

export interface YoYRow {
  year: number;
  month: number;
  month_label: string;
  current?: {
    activities?: number;
    distance_m?: number;
    duration_s?: number;
    tss?: number;
  } | null;
  previous_year?: {
    activities?: number;
    distance_m?: number;
    duration_s?: number;
    tss?: number;
  } | null;
  deltas?: {
    distance_pct?: number;
    duration_pct?: number;
    activities_pct?: number;
  } | null;
}

export interface YoYPayload {
  end_date: string;
  months: number;
  rows: YoYRow[];
  disclaimer?: string;
}

export interface PerformanceRecoveryMonth {
  month: string;
  month_start?: string;
  month_end?: string;
  volume_hours?: number | null;
  activity_count?: number | null;
  ctl?: number | null;
  hrv_delta_pct?: number | null;
}

export interface PerformanceRecoveryPayload {
  end_date: string;
  months: PerformanceRecoveryMonth[];
  disclaimer?: string;
}

export interface HistoryAnnotation {
  date?: string;
  type?: string;
  title?: string;
  detail?: string;
}

export interface HistoryAnnotationsPayload {
  end_date: string;
  items: HistoryAnnotation[];
  disclaimer?: string;
}
