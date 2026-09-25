export interface CoachingEvidenceOverview {
  canonical_recommendation_count: number;
  mature_execution_count: number;
  pending_count: number;
  short_term_outcome_count: number;
  medium_term_outcome_count: number;
  evidence_level: string | null;
  evidence_label: string;
  feedback_count: number;
  feedback_coverage: number | null;
  explicit_match_count: number;
  legacy_match_count: number;
  explicit_matching_share: number | null;
  model_version?: string | null;
  model_status?: string | null;
}

export interface CoachingObservationLink {
  recommendation_id?: number;
  as_of_date?: string;
  activity_id?: string | null;
  execution_status?: string | null;
  match_source?: string | null;
  short_term_maturity?: string | null;
  short_term_utility?: number | null;
}

export interface CoachingTypeEvidence {
  workout_type: string;
  label: string;
  recommendation_count: number;
  execution_count: number;
  mature_outcome_count: number;
  pending_count: number;
  incomplete_count: number;
  short_term_outcome: number | null;
  short_term_sample_count: number;
  medium_term_outcome: number | null;
  medium_term_sample_count: number;
  session_quality: number | null;
  session_quality_sample_count: number;
  observed_recovery_response: number | null;
  observed_recovery_sample_count: number;
  feedback_count: number;
  evidence_level: string | null;
  evidence_label: string;
  conclusion_strength: string;
  conclusion_strength_label?: string;
  observations: CoachingObservationLink[];
}

export interface CoachingInsight {
  code?: string;
  workout_type?: string;
  title?: string;
  sample_count?: number;
  evidence_level?: string;
  evidence_label?: string;
  conclusion_strength?: string;
  text: string;
}

export interface CoachingEvidencePayload {
  status: string;
  read_only: boolean;
  period: { start: string; end: string; window_days: number; allowed_windows: number[] };
  maturity_legend: Array<{ status: string; label: string; text: string }>;
  overview: CoachingEvidenceOverview;
  effectiveness: CoachingTypeEvidence[];
  feasibility: {
    followed: number;
    modified: number;
    replaced: number;
    skipped: number;
    pending: number;
    adherence: number | null;
    adherence_sample_count: number;
    evidence_label: string;
    note: string;
  };
  confidence: {
    sample_count: number;
    brier_score: number | null;
    expected_calibration_error: number | null;
    status: string;
    coverage: number | null;
    note?: string;
  };
  evidence_quality: {
    raw_sample_count: number;
    effective_sample_count: number;
    spread_days: number | null;
    sufficiency_level: string | null;
    sufficiency_label: string;
    explicit_execution_matches: number;
    legacy_heuristic_matches: number;
    pending_windows: number;
    incomplete_windows: number;
  };
  signals: {
    objective: { sources: string[]; short_term_sample_count: number; session_quality_sample_count: number };
    subjective: {
      sources: string[];
      sample_count: number;
      coverage: number | null;
      provenance: string;
      ground_truth: boolean;
    };
  };
  operations: {
    abstention: { status: string; sample_count: number };
    shadow: { status: string; note?: string };
    distribution: { unexpected_shift: boolean; types_from_zero: string[] };
  };
  operations_lines?: Array<{ code: string; label: string; text: string }>;
  what_we_know: CoachingInsight[];
  what_we_do_not_know: CoachingInsight[];
  do_not_change: string[];
  do_not_change_nb?: string[];
}

export interface QuickFeelOption {
  value: string;
  label: string;
}

export interface ActivityFeedback {
  id: number;
  activity_id: string;
  session_feel: string | null;
  rpe: number | null;
  legs: string | null;
  pain: number | null;
  motivation: number | null;
  notes: string | null;
}

export interface ActivityFeedbackPayload {
  status: string;
  activity_id: string;
  feedback: ActivityFeedback | null;
  quick_feel: QuickFeelOption[];
  rpe: { min: number; max: number };
  pain: { min: number; max: number };
  motivation: { min: number; max: number };
  legs: string[];
}

export interface FeedbackPromptPayload {
  status: string;
  activity_id: string;
  should_prompt: boolean;
  priority: string;
  reasons: string[];
  already_has_feedback: boolean;
}
