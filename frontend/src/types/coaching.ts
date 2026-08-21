/** Coaching cockpit TypeScript contracts — mirror backend summary payloads. */

export type FreshnessStatus = "fresh" | "aging" | "stale" | "missing";
export type TrendDirection = "up" | "flat" | "down" | "uncertain";
export type DecisionStatus = "recommend" | "weak_preference" | "abstain" | "insufficient_data" | string;

export interface FreshnessEntry {
  metric: string;
  observed_at?: string | null;
  age_days?: number | null;
  status: FreshnessStatus;
  freshness?: FreshnessStatus;
  source_type?: string;
}

export interface AthleteStateDimension {
  value?: number | string | null;
  trend?: TrendDirection | string | null;
  label?: string;
}

export interface AthleteStateSummary {
  fitness?: AthleteStateDimension;
  recovery?: AthleteStateDimension;
  fatigue?: AthleteStateDimension;
  [key: string]: AthleteStateDimension | undefined;
}

export interface DecisionReason {
  code: string;
  impact?: number;
  evidence_strength?: number;
  doc?: string;
  factor?: string;
}

export interface DecisionExplanation {
  decision?: string | null;
  reason_codes?: string[];
  guardrails?: string[];
  alternatives?: Array<Record<string, unknown>>;
  data_quality?: number | Record<string, unknown> | null;
  evidence_strength?: number | null;
  decision_confidence?: number | null;
  top_reasons?: DecisionReason[];
  guardrails_triggered?: string[];
  data_freshness?: Record<string, FreshnessEntry>;
}

export interface WorkoutPrescription {
  total_duration_min?: number | number[];
  warm_up?: Record<string, unknown>;
  main_set?: {
    repetitions?: number;
    work_duration_min?: number;
    recovery_duration_min?: number;
    target_hr?: number[];
    target_pace_sec_km?: number[];
    [key: string]: unknown;
  };
  cool_down?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface NextWorkout {
  workout_type?: string | null;
  duration_min?: number | number[] | null;
  target_hr?: number[] | null;
  target_pace?: number[] | null;
  rationale?: string | null;
  decision_status?: DecisionStatus;
  data_quality?: number | null;
  evidence_strength?: number | null;
  decision_confidence?: number | null;
}

export interface WeeklyPlanSession {
  day_offset?: number;
  type?: string;
  duration_min?: number | number[] | null;
  status?: "planned" | "completed" | "modified" | "missed" | string;
}

export interface TrainingPhaseDetail {
  phase?: string;
  confidence?: number;
  days_to_event?: number | null;
  primary_objectives?: string[];
  secondary_objectives?: string[];
  training_block?: string;
  goal_type?: string;
  reasons?: string[];
  [key: string]: unknown;
}

export interface WeeklyPlan {
  plan_id?: number | null;
  version?: number | null;
  week_objective?: string | null;
  sessions?: WeeklyPlanSession[];
}

export interface CoachingBrief {
  date?: string;
  athlete_state_summary?: AthleteStateSummary;
  recommendation?: NextWorkout;
  workout_prescription?: WorkoutPrescription;
  why?: DecisionReason[];
  guardrails?: string[];
  decision_explanation?: DecisionExplanation;
  plan?: WeeklyPlan;
  plan_stability?: string;
  warnings?: string[];
  system_health?: string;
  model_health?: string;
  data_freshness?: Record<string, FreshnessEntry>;
  evidence?: {
    data_quality?: number;
    evidence_strength?: number;
    decision_confidence?: number;
    confidence_reduced?: boolean;
    quality_factors?: string[];
  };
  goal?: Record<string, unknown> | null;
  training_phase?: string | TrainingPhaseDetail | null;
  key_evidence?: Array<Record<string, unknown>>;
}

export interface TodayDashboard {
  date: string;
  brief: CoachingBrief;
  system_attention: boolean;
  system_status?: string;
  system_issues?: string[];
  data_freshness?: Record<string, FreshnessEntry>;
  reason_docs?: Record<string, string>;
  persisted?: boolean;
  note?: string;
}

export interface PlanSummary {
  date: string;
  plan?: WeeklyPlan;
  plan_stability?: string;
  plan_adaptation?: Record<string, unknown>;
  goal?: Record<string, unknown> | null;
  training_phase?: string | null;
  training_phase_detail?: TrainingPhaseDetail | null;
  projected_week?: Record<string, unknown>;
}

export interface ProgressSummary {
  date: string;
  athlete_state_summary?: AthleteStateSummary;
  ctl?: number | null;
  atl?: number | null;
  tsb?: number | null;
  hrv_delta_pct?: number | null;
  rhr_delta_bpm?: number | null;
  drill_down?: Record<string, string>;
}

export interface InsightsSummary {
  date: string;
  concept_drift?: {
    overall?: string;
    relationships?: Array<Record<string, unknown>>;
    note?: string;
  };
  prospective?: Record<string, unknown>;
  drill_down?: Record<string, string>;
}

export interface SystemHealthPayload {
  date: string;
  health?: {
    status?: string;
    issues?: string[];
    checks?: Record<string, unknown>;
    findings?: Array<Record<string, unknown>>;
  };
  integrity?: {
    status?: string;
    findings?: Array<Record<string, unknown>>;
  };
  sync_page?: string;
}
