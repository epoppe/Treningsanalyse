/** Plan cockpit API contracts. */

export interface PlannedSessionDetail {
  day_offset?: number;
  type?: string;
  duration_min?: number | number[];
  purpose?: string;
  prescription?: Record<string, unknown>;
}

export interface PlanVersionEntry {
  version?: number;
  created_at?: string;
  changes?: Array<Record<string, unknown>>;
  reason?: string[];
  week_objective?: string;
  session_count?: number;
}

export interface PlanVsActualDay {
  date?: string;
  day_offset?: number;
  weekday?: number;
  planned_type?: string;
  planned_duration_min?: number | number[];
  actual_type?: string;
  actual_duration_min?: number;
  execution_status?: string;
  activity_id?: string;
  activity_name?: string;
  adherence?: number;
}

export interface MesocycleWeek {
  week?: number;
  week_index?: number;
  week_start?: string;
  phase?: string;
  target_volume?: number[];
  quality_sessions?: number;
  long_run_target_min?: number[];
  primary_stimulus?: string;
  secondary_stimulus?: string;
  deload_state?: string;
  source?: string;
  evidence_strength?: number;
}

export interface PlanDashboardPayload {
  status?: string;
  as_of?: string;
  week_start?: string;
  source?: "stored" | "live" | string;
  goal?: Record<string, unknown>;
  training_phase?: Record<string, unknown>;
  weekly_plan?: {
    plan_id?: number | null;
    version?: number;
    week_objective?: string;
    sessions?: PlannedSessionDetail[];
    target_volume_min?: number | number[];
    hard_sessions?: number;
    scores?: Record<string, unknown>;
  };
  mesocycle?: {
    start?: string;
    weeks?: number;
    selected_candidate?: string;
    mesocycle?: MesocycleWeek[];
    goal?: Record<string, unknown>;
    source?: string;
    evidence_strength?: number;
    note?: string;
  };
  plan_adaptation?: {
    plan_status?: string;
    changes?: Array<Record<string, unknown>>;
    reason?: string[];
    confidence?: number;
    signals?: Record<string, unknown>;
    note?: string;
  };
  plan_stability?: string;
  plan_stability_detail?: Record<string, unknown>;
  version_history?: PlanVersionEntry[];
  vs_actual?: {
    week_start?: string;
    days?: PlanVsActualDay[];
    summary?: {
      planned_count?: number;
      completed_count?: number;
      missed_count?: number;
      completion_rate?: number | null;
    };
  };
}
