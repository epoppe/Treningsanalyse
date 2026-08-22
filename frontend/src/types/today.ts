/** Today cockpit API contracts. */

export type DecisionStatus = "recommend" | "abstain" | "insufficient_data" | string;

export interface WorkoutPrescription {
  title?: string;
  total_duration_min?: number;
  warmup?: { duration_min?: number; intensity?: string };
  main_set?: {
    repetitions?: number;
    work_duration_min?: number;
    recovery_duration_min?: number;
    recovery_type?: string;
    target_hr?: number | number[];
    target_pace?: number | number[];
    target_rpe?: number | number[];
  };
  cooldown_min?: number;
  stimulus?: string;
  structure?: string;
  target_hr?: number | number[];
  target_pace?: number | number[];
  target_rpe?: number | number[];
  intensity_source?: string;
  pace_certainty?: string;
}

export interface DecisionReason {
  code?: string;
  impact?: number;
  evidence_strength?: number;
  doc?: string;
  factor?: string;
}

export interface DecisionExplanation {
  decision?: string;
  decision_status?: DecisionStatus;
  top_reasons?: DecisionReason[];
  reason_codes?: string[];
  guardrails?: string[];
  guardrails_triggered?: string[] | boolean;
  alternatives?: Array<Record<string, unknown>>;
  data_quality?: number;
  evidence_strength?: number;
  decision_confidence?: number;
  data_freshness?: Record<string, { status?: string; age_days?: number; freshness?: string }>;
  inputs?: Array<Record<string, unknown>>;
  note?: string;
}

export interface AthleteStateDimension {
  key: string;
  label: string;
  value?: number | null;
  trend?: string | null;
  status?: string | null;
  summary?: Record<string, unknown>;
}

export interface AthleteStatePayload {
  readiness_label?: string;
  dimensions?: AthleteStateDimension[];
  durability?: AthleteStateDimension;
  aerobic_efficiency?: AthleteStateDimension;
  raw?: Record<string, unknown>;
}

export interface PlannedSession {
  day_offset?: number;
  type?: string;
  duration_min?: number;
  purpose?: string;
}

export interface TodayDashboardPayload {
  as_of?: string;
  generated_at?: string;
  status?: string;
  persisted?: boolean;
  current_recommendation_id?: number | null;
  athlete_state?: AthleteStatePayload;
  recommendation?: {
    decision_status?: DecisionStatus;
    workout_type?: string;
    workout?: {
      type?: string;
      duration_min?: number;
      target_hr?: number | number[];
      target_pace?: number | number[];
      rationale?: string;
    };
    prescription?: WorkoutPrescription | null;
    safe_alternatives?: Array<Record<string, unknown>>;
    confidence?: number;
    evidence_strength?: number;
    data_quality?: number;
  };
  decision_explanation?: DecisionExplanation;
  why?: DecisionReason[];
  weekly_plan?: {
    plan_id?: number | null;
    version?: number;
    week_objective?: string;
    sessions?: PlannedSession[];
  };
  goal?: Record<string, unknown>;
  training_phase?: Record<string, unknown>;
  key_trends?: Array<{
    metric?: string;
    label?: string;
    direction?: string;
    relative_change_pct?: number | null;
    current?: number | null;
  }>;
  freshness?: Record<string, unknown>;
  warnings?: string[];
  system_status?: string;
  plan_adaptation?: Record<string, unknown>;
  plan_stability?: string;
  evidence?: Record<string, unknown>;
}
