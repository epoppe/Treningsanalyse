"""Lightweight metric registry — no DB table. Single source of truth for producers."""

from __future__ import annotations

from typing import Any, Dict, Optional


METRIC_REGISTRY: Dict[str, Dict[str, Any]] = {
    "ctl": {
        "canonical_producer": "PpapMetricsService.get_ctl",
        "units": "banister_fitness",
        "freshness_key": "calibration_snapshot",
        "fallback": None,
        "as_of": "day",
    },
    "atl": {
        "canonical_producer": "PpapMetricsService.get_atl",
        "units": "banister_fatigue",
        "freshness_key": "calibration_snapshot",
        "fallback": None,
        "as_of": "day",
    },
    "tsb": {
        "canonical_producer": "PpapMetricsService.get_tsb",
        "units": "ctl_minus_atl",
        "freshness_key": "calibration_snapshot",
        "fallback": None,
        "as_of": "day",
    },
    "hrv_delta_pct": {
        "canonical_producer": "PpapMetricsService.get_hrv_delta_pct",
        "units": "percent_vs_baseline",
        "freshness_key": "hrv_baseline",
        "fallback": "missing_not_negative",
        "as_of": "day",
    },
    "rhr_delta_bpm": {
        "canonical_producer": "PpapMetricsService.get_rhr_delta_bpm",
        "units": "bpm_vs_baseline",
        "freshness_key": "hrv_baseline",
        "fallback": "missing_not_negative",
        "as_of": "day",
    },
    "lt1": {
        "canonical_producer": "AdaptiveThresholdService.estimate_lt1",
        "units": "hr_bpm_and_or_pace",
        "freshness_key": "lt2",
        "fallback": "lt2_multiplier",
        "as_of": "end_date",
    },
    "lt2": {
        "canonical_producer": "AdaptiveThresholdService.latest_lt2",
        "units": "hr_bpm",
        "freshness_key": "lt2",
        "fallback": "aging_ok_not_primary",
        "as_of": "end_date",
    },
    "critical_speed": {
        "canonical_producer": "PpapMetricsService.get_critical_speed_snapshot",
        "units": "m_per_s",
        "freshness_key": "critical_speed",
        "fallback": None,
        "as_of": "day",
    },
    "vo2max": {
        "canonical_producer": "GarminPerformanceMetric.vo2_max_precise",
        "units": "ml_kg_min",
        "freshness_key": "vo2max",
        "fallback": None,
        "as_of": "observed_at",
    },
    "durability": {
        "canonical_producer": "CoachingDecisionMetricsService.get_durability_score",
        "units": "score_0_100",
        "freshness_key": "calibration_snapshot",
        "fallback": "low_confidence",
        "as_of": "day",
    },
    "efficiency_factor": {
        "canonical_producer": "PpapMetricsService.get_ef_rolling",
        "units": "ef",
        "freshness_key": "calibration_snapshot",
        "fallback": None,
        "as_of": "day",
    },
    "weekly_load": {
        "canonical_producer": "LoadVariabilityService._daily_loads (sum) / LoadProgressionService minutes",
        "units": "tss_or_minutes",
        "freshness_key": "calibration_snapshot",
        "fallback": 0,
        "as_of": "week_end",
        "note": "Prefer LoadProgressionService for volume minutes; LoadVariability for TSS monotony",
    },
    "monotony": {
        "canonical_producer": "LoadVariabilityService.analyze",
        "units": "foster_mean_over_std",
        "freshness_key": "calibration_snapshot",
        "fallback": None,
        "as_of": "day",
    },
    "session_classification": {
        "canonical_producer": "SessionClassifierService.classify_activity",
        "units": "session_type_enum",
        "freshness_key": None,
        "fallback": "unknown",
        "as_of": "end_date",
    },
    "readiness": {
        "canonical_producer": "PpapMetricsService.get_readiness_component('readiness.total_score')",
        "units": "garmin_0_100",
        "freshness_key": "hrv_baseline",
        "fallback": "missing",
        "as_of": "day",
        "note": "Live coaching uses Garmin total_score — not MCP readiness_score composite",
    },
}


def get_metric_spec(metric: str) -> Optional[Dict[str, Any]]:
    return METRIC_REGISTRY.get(metric)


def lineage(
    metric: str,
    *,
    value: Any,
    observed_at: Optional[str] = None,
    freshness: Optional[str] = None,
    quality: Optional[float] = None,
    derived_from: Optional[list] = None,
) -> Dict[str, Any]:
    spec = get_metric_spec(metric) or {}
    return {
        "metric": metric,
        "value": value,
        "source": spec.get("canonical_producer"),
        "observed_at": observed_at,
        "freshness": freshness,
        "derived_from": derived_from or [],
        "quality": quality,
        "units": spec.get("units"),
    }
