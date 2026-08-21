"""Central coaching model-config constants — SAFETY stays explicit in call sites."""

from __future__ import annotations

# Classification: MODEL_CONFIG (tunable) vs SAFETY (do not casually change)

# --- MODEL_CONFIG ---
CTL_TAU_DAYS = 42
ATL_TAU_DAYS = 7
DEFAULT_HARD_SESSION_SPACING_HOURS = 36.0
DEFAULT_HRV_DROP_WARNING_PCT = -12.0
DEFAULT_RHR_RISE_WARNING_BPM = 4.0
PROSPECTIVE_LOW_N_HEALTH = 5
SHADOW_READINESS_MIN_N = 30
CONFIDENCE_BIN_MIN_N = 15
PLAN_CHURN_OVERREACTIVE_14D = 6
RECOMMENDATION_CHURN_SAME_DAY = 2

# --- PHYSIOLOGICAL_DEFAULT (documented defaults; overridable only with sufficiency) ---
DEFAULT_RECOVERY_COST = {
    "easy_run": [0, 1],
    "threshold": [1, 2],
    "vo2_intervals": [1, 3],
    "race": [3, 7],
}

# --- PRESENTATION ---
MONTHLY_REVIEW_SPARSE_N = 5
