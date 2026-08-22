"""Curated analytics metric registry for the /analyse workspace.

Reuses MCP DERIVED_METRIC_CATALOG keys and coaching decision metrics.
Does not invent new metric algorithms — metadata + dependency policy only.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Analytic roles (stimulus → load → recovery → adaptation → performance)
# ---------------------------------------------------------------------------

ROLE_STIMULUS = "stimulus"
ROLE_LOAD_STATE = "load_state"
ROLE_TRAINING_STRUCTURE = "training_structure"
ROLE_RECOVERY = "recovery"
ROLE_EXECUTION = "execution"
ROLE_FITNESS = "fitness"
ROLE_PERFORMANCE = "performance"
ROLE_CONTEXT = "context"

RELATIONSHIP_TYPES = (
    "SAME_TIME_ASSOCIATION",
    "LAGGED_ASSOCIATION",
    "TRAINING_RESPONSE",
    "MATHEMATICAL_DEPENDENCY",
    "PROSPECTIVE_EVIDENCE",
)

# Lag families (presets — not physiological truths)
LAG_FAMILIES: Dict[str, List[int]] = {
    "recovery": [0, 1, 2, 3],
    "session_quality": [0, 1, 3, 7],
    "aerobic_efficiency": [7, 14, 21, 28],
    "threshold_cs": [14, 21, 28, 42],
    "durability": [14, 21, 28, 42],
    "race_block": [28, 42, 56],
}

# Mathematical / shared-component dependencies (undirected for blocking)
# DIRECT_DEPENDENCY: one is algebraically derived from the other (or transform)
# SHARED_COMPONENT: both include a shared input component
DIRECT_DEPENDENCIES: Set[frozenset] = {
    frozenset({"fitness.ctl", "fitness.tsb"}),
    frozenset({"fitness.atl", "fitness.tsb"}),
    frozenset({"fitness.ctl", "fitness.form"}),
    frozenset({"fitness.atl", "fitness.form"}),
    frozenset({"fitness.tsb", "fitness.form"}),  # form ≡ tsb
    frozenset({"fitness.tsb", "readiness.form_component"}),
    frozenset({"fitness.form", "readiness.form_component"}),
    frozenset({"readiness.total_score", "readiness.sleep_component"}),
    frozenset({"readiness.total_score", "readiness.hrv_component"}),
    frozenset({"readiness.total_score", "readiness.form_component"}),
    frozenset({"cardio.hrv_7d", "recovery.hrv_delta_pct"}),
    frozenset({"recovery.hrv_baseline", "recovery.hrv_delta_pct"}),
    frozenset({"load.monotony", "load.strain"}),  # strain = monotony * load
    frozenset({"coaching.zone1_pct", "coaching.polarization_score"}),
    frozenset({"coaching.zone2_pct", "coaching.polarization_score"}),
    frozenset({"coaching.zone3_pct", "coaching.polarization_score"}),
}

SHARED_COMPONENTS: Set[frozenset] = {
    frozenset({"fitness.ctl", "fitness.atl"}),  # both from load series
    frozenset({"fitness.ctl", "fitness.gain_rate"}),
    frozenset({"cardio.hrv_7d", "readiness.hrv_component"}),
    frozenset({"recovery.hrv_delta_pct", "readiness.hrv_component"}),
    frozenset({"sleep.sleep_debt_7d", "readiness.sleep_component"}),
}


def _m(
    key: str,
    *,
    label: str,
    analytic_role: str,
    category: str,
    scope: str,
    unit: str,
    direction: str = "higher_is_better",
    selectable_x: bool = True,
    selectable_y: bool = True,
    supports_lag: bool = True,
    supports_trend: bool = True,
    supports_period_comparison: bool = True,
    minimum_samples: int = 12,
    source_type: str = "computed",
    dependencies: Optional[List[str]] = None,
    recommended_lags_days: Optional[List[int]] = None,
    group: str = "Advanced",
    explanation: str = "",
    expose_default: bool = True,
) -> Dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "analytic_role": analytic_role,
        "category": category,
        "scope": scope,
        "unit": unit,
        "direction": direction,
        "selectable_x": selectable_x,
        "selectable_y": selectable_y,
        "supports_lag": supports_lag,
        "supports_trend": supports_trend,
        "supports_period_comparison": supports_period_comparison,
        "minimum_samples": minimum_samples,
        "source_type": source_type,
        "dependencies": dependencies or [],
        "recommended_lags_days": recommended_lags_days or [],
        "group": group,
        "explanation": explanation,
        "expose_default": expose_default,
    }


# Curated longitudinal surface for /analyse (not the full MCP catalog)
ANALYTICS_METRICS: Dict[str, Dict[str, Any]] = {
    # --- LOAD STATE ---
    "fitness.ctl": _m(
        "fitness.ctl",
        label="CTL (form)",
        analytic_role=ROLE_LOAD_STATE,
        category="fitness",
        scope="daily",
        unit="load",
        group="Load",
        explanation="Chronic training load (Banister fitness).",
        recommended_lags_days=[0],
        supports_lag=False,
        dependencies=["load_series"],
    ),
    "fitness.atl": _m(
        "fitness.atl",
        label="ATL (fatigue)",
        analytic_role=ROLE_LOAD_STATE,
        category="fitness",
        scope="daily",
        unit="load",
        direction="lower_is_better",
        group="Load",
        explanation="Acute training load (Banister fatigue).",
        supports_lag=False,
        dependencies=["load_series"],
    ),
    "fitness.tsb": _m(
        "fitness.tsb",
        label="TSB (form surplus)",
        analytic_role=ROLE_LOAD_STATE,
        category="fitness",
        scope="daily",
        unit="load",
        group="Load",
        explanation="CTL − ATL. Mathematically dependent on CTL/ATL.",
        supports_lag=False,
        dependencies=["fitness.ctl", "fitness.atl"],
    ),
    "fitness.gain_rate": _m(
        "fitness.gain_rate",
        label="CTL gain rate",
        analytic_role=ROLE_LOAD_STATE,
        category="fitness",
        scope="daily",
        unit="load_per_day",
        group="Advanced",
        explanation="Rate of chronic load change over recent weeks.",
        recommended_lags_days=[0, 7],
        dependencies=["fitness.ctl"],
    ),
    "load.monotony": _m(
        "load.monotony",
        label="Load monotony",
        analytic_role=ROLE_LOAD_STATE,
        category="training_load",
        scope="daily",
        unit="ratio",
        direction="context",
        group="Load",
        explanation="Foster monotony (mean/std of recent daily loads).",
        recommended_lags_days=[0, 1, 3, 7],
    ),
    "load.strain": _m(
        "load.strain",
        label="Load strain",
        analytic_role=ROLE_LOAD_STATE,
        category="training_load",
        scope="daily",
        unit="score",
        direction="context",
        group="Load",
        explanation="Monotony × load (Foster strain).",
        dependencies=["load.monotony"],
        recommended_lags_days=[0, 1, 3, 7],
    ),
    # --- TRAINING STRUCTURE ---
    "coaching.zone1_pct": _m(
        "coaching.zone1_pct",
        label="Zone 1 %",
        analytic_role=ROLE_TRAINING_STRUCTURE,
        category="coaching",
        scope="daily",
        unit="%",
        group="Training",
        explanation="Share of recent training below LT1 (easy).",
        recommended_lags_days=[7, 14, 28],
    ),
    "coaching.zone2_pct": _m(
        "coaching.zone2_pct",
        label="Zone 2 %",
        analytic_role=ROLE_TRAINING_STRUCTURE,
        category="coaching",
        scope="daily",
        unit="%",
        direction="context",
        group="Training",
        explanation="Share of recent training between LT1 and LT2.",
        recommended_lags_days=[7, 14, 28],
    ),
    "coaching.zone3_pct": _m(
        "coaching.zone3_pct",
        label="Zone 3 %",
        analytic_role=ROLE_TRAINING_STRUCTURE,
        category="coaching",
        scope="daily",
        unit="%",
        direction="context",
        group="Training",
        explanation="Share of recent training above LT2 (hard).",
        recommended_lags_days=[7, 14, 28],
    ),
    "coaching.polarization_score": _m(
        "coaching.polarization_score",
        label="Polarization score",
        analytic_role=ROLE_TRAINING_STRUCTURE,
        category="coaching",
        scope="daily",
        unit="score",
        group="Advanced",
        explanation="How polarized recent intensity distribution is (from zone %).",
        dependencies=["coaching.zone1_pct", "coaching.zone2_pct", "coaching.zone3_pct"],
        recommended_lags_days=[14, 28],
    ),
    "consistency.score": _m(
        "consistency.score",
        label="Consistency score",
        analytic_role=ROLE_TRAINING_STRUCTURE,
        category="coaching",
        scope="daily",
        unit="score",
        group="Advanced",
        explanation="How consistently training has been executed recently.",
        recommended_lags_days=[14, 28],
    ),
    # --- RECOVERY ---
    "cardio.hrv_7d": _m(
        "cardio.hrv_7d",
        label="HRV RMSSD (7d)",
        analytic_role=ROLE_RECOVERY,
        category="cardio",
        scope="daily",
        unit="ms",
        group="Recovery",
        explanation="Rolling 7-day HRV RMSSD.",
        recommended_lags_days=LAG_FAMILIES["recovery"],
    ),
    "recovery.hrv_delta_pct": _m(
        "recovery.hrv_delta_pct",
        label="HRV Δ%",
        analytic_role=ROLE_RECOVERY,
        category="recovery",
        scope="daily",
        unit="%",
        group="Recovery",
        explanation="HRV vs personal baseline (%).",
        dependencies=["recovery.hrv_baseline", "cardio.hrv_7d"],
        recommended_lags_days=LAG_FAMILIES["recovery"],
    ),
    "cardio.rhr_7d": _m(
        "cardio.rhr_7d",
        label="Resting HR (7d)",
        analytic_role=ROLE_RECOVERY,
        category="cardio",
        scope="daily",
        unit="bpm",
        direction="lower_is_better",
        group="Recovery",
        explanation="Rolling resting heart rate.",
        recommended_lags_days=LAG_FAMILIES["recovery"],
    ),
    "readiness.total_score": _m(
        "readiness.total_score",
        label="Readiness (Garmin)",
        analytic_role=ROLE_RECOVERY,
        category="readiness",
        scope="daily",
        unit="score",
        group="Recovery",
        explanation="Garmin readiness total score.",
        dependencies=[
            "readiness.sleep_component",
            "readiness.hrv_component",
            "readiness.form_component",
        ],
        recommended_lags_days=[0, 1],
    ),
    "readiness.sleep_component": _m(
        "readiness.sleep_component",
        label="Readiness · sleep",
        analytic_role=ROLE_RECOVERY,
        category="readiness",
        scope="daily",
        unit="score",
        group="Recovery",
        explanation="Sleep component of Garmin readiness.",
        recommended_lags_days=[0, 1],
    ),
    "readiness.hrv_component": _m(
        "readiness.hrv_component",
        label="Readiness · HRV",
        analytic_role=ROLE_RECOVERY,
        category="readiness",
        scope="daily",
        unit="score",
        group="Recovery",
        explanation="HRV component of Garmin readiness.",
        recommended_lags_days=[0, 1],
    ),
    "readiness.form_component": _m(
        "readiness.form_component",
        label="Readiness · form",
        analytic_role=ROLE_RECOVERY,
        category="readiness",
        scope="daily",
        unit="score",
        group="Recovery",
        explanation="Form/TSB-weighted readiness component — linked to TSB.",
        dependencies=["fitness.tsb"],
        recommended_lags_days=[0],
        supports_lag=False,
    ),
    "sleep.sleep_debt_7d": _m(
        "sleep.sleep_debt_7d",
        label="Sleep debt (7d)",
        analytic_role=ROLE_RECOVERY,
        category="sleep",
        scope="daily",
        unit="hours",
        direction="lower_is_better",
        group="Recovery",
        explanation="Accumulated sleep debt over 7 days.",
        recommended_lags_days=[0, 1, 3],
    ),
    # --- FITNESS / ADAPTATION ---
    "fitness.ef_30d": _m(
        "fitness.ef_30d",
        label="Aerobic efficiency (EF30d)",
        analytic_role=ROLE_FITNESS,
        category="fitness",
        scope="daily",
        unit="m_per_s_per_bpm",
        group="Fitness",
        explanation="Rolling speed relative to heart rate on easy runs.",
        recommended_lags_days=LAG_FAMILIES["aerobic_efficiency"],
    ),
    "cardio.drift_score": _m(
        "cardio.drift_score",
        label="HR drift score",
        analytic_role=ROLE_FITNESS,
        category="cardio",
        scope="daily",
        unit="score",
        direction="lower_is_better",
        group="Fitness",
        explanation="Cardiac drift / decoupling pressure (heuristic).",
        recommended_lags_days=[7, 14, 28],
    ),
    "running.critical_speed": _m(
        "running.critical_speed",
        label="Critical speed",
        analytic_role=ROLE_FITNESS,
        category="running",
        scope="snapshot",
        unit="km/h",
        group="Fitness",
        explanation="Critical speed snapshot from duration curve.",
        recommended_lags_days=LAG_FAMILIES["threshold_cs"],
        supports_lag=True,
    ),
    "running.durability_score": _m(
        "running.durability_score",
        label="Durability",
        analytic_role=ROLE_FITNESS,
        category="running",
        scope="daily",
        unit="score",
        group="Advanced",
        explanation="Long-run durability / late-session resilience score.",
        recommended_lags_days=LAG_FAMILIES["durability"],
    ),
    "running.speed_5m_hist": _m(
        "running.speed_5m_hist",
        label="Best 5 min speed (365d)",
        analytic_role=ROLE_PERFORMANCE,
        category="running",
        scope="rolling_daily",
        unit="km/h",
        group="Performance",
        explanation="Rolling 365-day best 5-minute speed.",
        recommended_lags_days=[28, 42],
    ),
    "running.speed_10m_hist": _m(
        "running.speed_10m_hist",
        label="Best 10 min speed (365d)",
        analytic_role=ROLE_PERFORMANCE,
        category="running",
        scope="rolling_daily",
        unit="km/h",
        group="Performance",
        explanation="Rolling 365-day best 10-minute speed.",
        recommended_lags_days=[28, 42],
    ),
    "running.speed_20m_hist": _m(
        "running.speed_20m_hist",
        label="Best 20 min speed (365d)",
        analytic_role=ROLE_PERFORMANCE,
        category="running",
        scope="rolling_daily",
        unit="km/h",
        group="Performance",
        explanation="Rolling 365-day best 20-minute speed.",
        recommended_lags_days=[28, 42],
    ),
    "running.speed_60m_hist": _m(
        "running.speed_60m_hist",
        label="Best 60 min speed (365d)",
        analytic_role=ROLE_PERFORMANCE,
        category="running",
        scope="rolling_daily",
        unit="km/h",
        group="Performance",
        explanation="Rolling 365-day best 60-minute speed.",
        recommended_lags_days=[28, 56],
    ),
}

# Stimulus aggregates (computed in analysis layer from sessions — not MCP daily keys)
STIMULUS_AGGREGATES: Dict[str, Dict[str, Any]] = {
    "stimulus.easy_minutes_7d": {
        "key": "stimulus.easy_minutes_7d",
        "label": "Easy minutes (7d)",
        "analytic_role": ROLE_STIMULUS,
        "aggregation_days": 7,
        "stimulus_kind": "easy_volume",
        "group": "Training",
        "recommended_lags_days": LAG_FAMILIES["aerobic_efficiency"],
        "selectable_x": True,
        "selectable_y": False,
        "supports_lag": True,
        "scope": "weekly",
        "unit": "min",
        "explanation": "Easy/zone-1 minutes summed over 7 days.",
    },
    "stimulus.easy_minutes_28d": {
        "key": "stimulus.easy_minutes_28d",
        "label": "Easy minutes (28d)",
        "analytic_role": ROLE_STIMULUS,
        "aggregation_days": 28,
        "stimulus_kind": "easy_volume",
        "group": "Training",
        "recommended_lags_days": LAG_FAMILIES["aerobic_efficiency"],
        "selectable_x": True,
        "selectable_y": False,
        "supports_lag": True,
        "scope": "weekly",
        "unit": "min",
        "explanation": "Easy/zone-1 minutes summed over 28 days.",
    },
    "stimulus.threshold_minutes_14d": {
        "key": "stimulus.threshold_minutes_14d",
        "label": "Threshold minutes (14d)",
        "analytic_role": ROLE_STIMULUS,
        "aggregation_days": 14,
        "stimulus_kind": "threshold_volume",
        "group": "Training",
        "recommended_lags_days": LAG_FAMILIES["threshold_cs"],
        "selectable_x": True,
        "selectable_y": False,
        "supports_lag": True,
        "scope": "weekly",
        "unit": "min",
        "explanation": "Threshold-zone minutes over 14 days.",
    },
    "stimulus.vo2_minutes_14d": {
        "key": "stimulus.vo2_minutes_14d",
        "label": "VO2 minutes (14d)",
        "analytic_role": ROLE_STIMULUS,
        "aggregation_days": 14,
        "stimulus_kind": "vo2_volume",
        "group": "Training",
        "recommended_lags_days": LAG_FAMILIES["threshold_cs"],
        "selectable_x": True,
        "selectable_y": False,
        "supports_lag": True,
        "scope": "weekly",
        "unit": "min",
        "explanation": "High-intensity / VO2 minutes over 14 days.",
    },
    "stimulus.long_run_minutes_28d": {
        "key": "stimulus.long_run_minutes_28d",
        "label": "Long-run minutes (28d)",
        "analytic_role": ROLE_STIMULUS,
        "aggregation_days": 28,
        "stimulus_kind": "long_run_volume",
        "group": "Training",
        "recommended_lags_days": LAG_FAMILIES["durability"],
        "selectable_x": True,
        "selectable_y": False,
        "supports_lag": True,
        "scope": "weekly",
        "unit": "min",
        "explanation": "Long-run oriented easy volume over 28 days (approx via easy zone).",
    },
    "stimulus.tss_7d": {
        "key": "stimulus.tss_7d",
        "label": "TSS (7d)",
        "analytic_role": ROLE_STIMULUS,
        "aggregation_days": 7,
        "stimulus_kind": "weekly_tss",
        "group": "Training",
        "recommended_lags_days": LAG_FAMILIES["recovery"],
        "selectable_x": True,
        "selectable_y": False,
        "supports_lag": True,
        "scope": "weekly",
        "unit": "tss",
        "explanation": "Training stress summed over 7 days.",
    },
    "stimulus.tss_28d": {
        "key": "stimulus.tss_28d",
        "label": "TSS (28d)",
        "analytic_role": ROLE_STIMULUS,
        "aggregation_days": 28,
        "stimulus_kind": "weekly_tss",
        "group": "Training",
        "recommended_lags_days": [14, 21, 28],
        "selectable_x": True,
        "selectable_y": False,
        "supports_lag": True,
        "scope": "weekly",
        "unit": "tss",
        "explanation": "Training stress summed over 28 days.",
    },
}

ANALYSIS_PRESETS: List[Dict[str, Any]] = [
    {
        "id": "aerobic_fitness",
        "title": "WHAT BUILDS MY AEROBIC FITNESS?",
        "outcome": "fitness.ef_30d",
        "predictors": [
            "stimulus.easy_minutes_28d",
            "stimulus.tss_28d",
            "consistency.score",
            "coaching.polarization_score",
            "coaching.zone1_pct",
        ],
        "lags": LAG_FAMILIES["aerobic_efficiency"],
        "mode": "TRAINING_RESPONSE",
    },
    {
        "id": "threshold",
        "title": "WHAT IMPROVES MY THRESHOLD?",
        "outcome": "running.critical_speed",
        "predictors": [
            "stimulus.threshold_minutes_14d",
            "stimulus.easy_minutes_28d",
            "consistency.score",
        ],
        "lags": LAG_FAMILIES["threshold_cs"],
        "mode": "TRAINING_RESPONSE",
    },
    {
        "id": "durability",
        "title": "WHAT IMPROVES MY DURABILITY?",
        "outcome": "running.durability_score",
        "predictors": [
            "stimulus.easy_minutes_28d",
            "stimulus.tss_28d",
            "consistency.score",
        ],
        "lags": LAG_FAMILIES["durability"],
        "mode": "TRAINING_RESPONSE",
    },
    {
        "id": "hrv_recovery",
        "title": "WHAT AFFECTS MY HRV?",
        "outcome": "recovery.hrv_delta_pct",
        "predictors": [
            "stimulus.tss_7d",
            "load.monotony",
            "sleep.sleep_debt_7d",
            "fitness.tsb",
        ],
        "lags": LAG_FAMILIES["recovery"],
        "mode": "LAGGED_ASSOCIATION",
    },
    {
        "id": "easy_helped",
        "title": "HAS MORE EASY TRAINING HELPED?",
        "outcome": "fitness.ef_30d",
        "predictors": ["stimulus.easy_minutes_28d", "coaching.zone1_pct"],
        "lags": LAG_FAMILIES["aerobic_efficiency"],
        "mode": "TRAINING_RESPONSE",
    },
    {
        "id": "load_hurts_recovery",
        "title": "DOES HIGH TRAINING LOAD HURT RECOVERY?",
        "outcome": "cardio.hrv_7d",
        "predictors": ["stimulus.tss_7d", "load.strain", "fitness.atl"],
        "lags": LAG_FAMILIES["recovery"],
        "mode": "LAGGED_ASSOCIATION",
    },
    {
        "id": "hard_sessions",
        "title": "WHAT MAKES HARD SESSIONS SUCCESSFUL?",
        "outcome": "fitness.ef_30d",
        "predictors": [
            "stimulus.tss_7d",
            "cardio.hrv_7d",
            "sleep.sleep_debt_7d",
            "fitness.tsb",
        ],
        "lags": LAG_FAMILIES["session_quality"],
        "mode": "LAGGED_ASSOCIATION",
    },
    {
        "id": "best_races",
        "title": "WHAT PRECEDED MY BEST RACES?",
        "outcome": "running.speed_20m_hist",
        "predictors": [
            "stimulus.easy_minutes_28d",
            "stimulus.threshold_minutes_14d",
            "consistency.score",
            "coaching.polarization_score",
        ],
        "lags": LAG_FAMILIES["race_block"],
        "mode": "PROSPECTIVE_EVIDENCE",
    },
]

MATRIX_PREDICTORS = [
    "sleep.sleep_debt_7d",
    "cardio.hrv_7d",
    "cardio.rhr_7d",
    "stimulus.easy_minutes_28d",
    "stimulus.threshold_minutes_14d",
    "stimulus.tss_28d",
    "fitness.gain_rate",
    "fitness.tsb",
    "consistency.score",
    "coaching.polarization_score",
]

MATRIX_OUTCOMES = [
    "fitness.ef_30d",
    "running.critical_speed",
    "running.durability_score",
    "running.speed_20m_hist",
    "recovery.hrv_delta_pct",
    "readiness.total_score",
]


def list_analytics_metrics(*, include_stimulus: bool = True) -> List[Dict[str, Any]]:
    items = [dict(v) for v in ANALYTICS_METRICS.values() if v.get("expose_default", True)]
    if include_stimulus:
        items.extend(dict(v) for v in STIMULUS_AGGREGATES.values())
    return sorted(items, key=lambda m: (m.get("group") or "", m.get("label") or m["key"]))


def get_analytics_metric(key: str) -> Optional[Dict[str, Any]]:
    if key in ANALYTICS_METRICS:
        return dict(ANALYTICS_METRICS[key])
    if key in STIMULUS_AGGREGATES:
        return dict(STIMULUS_AGGREGATES[key])
    return None


def dependency_relation(a: str, b: str) -> str:
    """Return DIRECT_DEPENDENCY | SHARED_COMPONENT | INDEPENDENT_OR_UNKNOWN."""
    if a == b:
        return "DIRECT_DEPENDENCY"
    pair = frozenset({a, b})
    # Also map form ≡ tsb aliases
    aliases = {
        "fitness.form": "fitness.tsb",
    }
    a2 = aliases.get(a, a)
    b2 = aliases.get(b, b)
    pair2 = frozenset({a2, b2})
    if pair in DIRECT_DEPENDENCIES or pair2 in DIRECT_DEPENDENCIES:
        return "DIRECT_DEPENDENCY"
    if pair in SHARED_COMPONENTS or pair2 in SHARED_COMPONENTS:
        return "SHARED_COMPONENT"
    # Check registry-declared dependencies
    ma = get_analytics_metric(a2)
    mb = get_analytics_metric(b2)
    deps_a = set((ma or {}).get("dependencies") or [])
    deps_b = set((mb or {}).get("dependencies") or [])
    if b2 in deps_a or a2 in deps_b:
        return "DIRECT_DEPENDENCY"
    if deps_a & deps_b:
        return "SHARED_COMPONENT"
    return "INDEPENDENT_OR_UNKNOWN"


def should_suppress_correlation(a: str, b: str, *, advanced: bool = False) -> Tuple[bool, str]:
    rel = dependency_relation(a, b)
    if rel == "DIRECT_DEPENDENCY":
        return True, (
            "These metrics are mathematically related and are therefore not suitable "
            "for independent correlation analysis."
        )
    if rel == "SHARED_COMPONENT" and not advanced:
        return True, (
            "These metrics share a common component. Correlation may be trivial — "
            "enable advanced mode to inspect with a warning."
        )
    return False, ""


def recommended_outcomes_for(predictor: str) -> List[str]:
    role = (get_analytics_metric(predictor) or {}).get("analytic_role")
    if role in {ROLE_STIMULUS, ROLE_TRAINING_STRUCTURE}:
        return [
            "fitness.ef_30d",
            "running.durability_score",
            "running.critical_speed",
            "running.speed_20m_hist",
        ]
    if role == ROLE_LOAD_STATE:
        return ["cardio.hrv_7d", "recovery.hrv_delta_pct", "readiness.total_score"]
    if role == ROLE_RECOVERY:
        return ["fitness.ef_30d", "running.speed_20m_hist"]
    return ["fitness.ef_30d"]


def catalog_payload() -> Dict[str, Any]:
    metrics = list_analytics_metrics()
    groups: Dict[str, List[str]] = {}
    for m in metrics:
        groups.setdefault(m.get("group") or "Other", []).append(m["key"])
    return {
        "metrics": metrics,
        "groups": groups,
        "presets": ANALYSIS_PRESETS,
        "matrix": {"predictors": MATRIX_PREDICTORS, "outcomes": MATRIX_OUTCOMES},
        "lag_families": LAG_FAMILIES,
        "relationship_types": list(RELATIONSHIP_TYPES),
        "disclaimer": (
            "Relationships are observational associations over time — not causal claims. "
            "Mathematically dependent pairs are suppressed by default."
        ),
    }
