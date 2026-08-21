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
      points: TimeseriesPoint[];
      sample_count: number;
      missing_days_approx?: number;
      unit_note?: string;
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
}
