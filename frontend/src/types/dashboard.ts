/** What-changed and post-sync dashboard contracts. */

export interface MaterialChange {
  metric: string;
  label: string;
  before?: number | string;
  after?: number | string;
  direction?: string;
  materiality?: string;
}

export interface WhatChangedPayload {
  status?: string;
  as_of?: string;
  generated_at?: string;
  material_changes: MaterialChange[];
  recommendation_changed: boolean;
  before_recommendation?: string | null;
  after_recommendation?: string | null;
  reason_codes_added?: string[];
  reason_codes_removed?: string[];
  has_material_change?: boolean;
  summary?: string;
}

export interface PostSyncSummaryPayload {
  status?: string;
  activity_id?: string;
  activity_name?: string;
  session_type?: string;
  session_quality?: {
    label?: string;
    score?: number | null;
    flags?: string[];
    confidence?: number | null;
  };
  comparable?: {
    count?: number;
    percentile?: number | null;
    comparison_label?: string | null;
    limitations?: string[];
  };
  interpretation?: string;
  plan_effect?: { note?: string };
}

export interface RecommendationHistoryItem {
  id?: number;
  as_of_date?: string;
  generated_at?: string;
  recommended?: string;
  decision_status?: string;
  is_active?: boolean;
  evidence_strength?: number;
  decision_confidence?: number;
}

export interface RecommendationHistoryPayload {
  status?: string;
  items: RecommendationHistoryItem[];
  count: number;
}
