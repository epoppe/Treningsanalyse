"""Canonical temporal metadata for metrics exposed in /analyse.

Producer units stay in the coaching registry and calculation services.
Display units are applied only at the presentation boundary.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from statistics import median
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .ppap_metrics_service import DURATION_CURVE_METRICS, ROLLING_CURVE_LOOKBACK_DAYS

MPS_TO_KMH = 3.6

TEMPORAL_SEMANTICS = (
    "observation",
    "snapshot",
    "rolling_mean",
    "rolling_median",
    "rolling_best",
    "cumulative",
    "derived_state",
)


@dataclass(frozen=True)
class TemporalMetricContract:
    key: str
    canonical_producer: str
    canonical_unit: str
    display_unit: str
    display_multiplier: float
    temporal_semantics: str
    native_cadence_days: int
    aggregation_type: str
    smoothing_window_days: Optional[int]
    direction: str
    supports_as_of: bool
    supports_trend: bool
    supports_period_comparison: bool
    source_type: str
    dependencies: Tuple[str, ...] = ()
    period_summary: str = "median"
    meaningful_change_fallback_relative_pct: float = 5.0
    meaningful_change_minimum_absolute: float = 0.0
    aggregation_window_days: Optional[int] = None
    lookback_days: Optional[int] = None

    @property
    def show_gaps(self) -> bool:
        """Daily observations should expose holes. Snapshots and rolling bests need not."""
        if self.temporal_semantics in {"snapshot", "rolling_best"}:
            return False
        return self.native_cadence_days <= 1

    def public_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["dependencies"] = list(self.dependencies)
        payload["show_gaps"] = self.show_gaps
        payload["meaningful_change"] = {
            "method": "personal_variability",
            "fallback_relative_pct": self.meaningful_change_fallback_relative_pct,
            "minimum_absolute": self.meaningful_change_minimum_absolute,
            "note": "Heuristic personal noise (MAD of changes). Not a physiological constant.",
        }
        return payload


def _c(**kwargs: Any) -> TemporalMetricContract:
    return TemporalMetricContract(**kwargs)


def _speed_contract(key: str, *, hist: bool) -> TemporalMetricContract:
    return _c(
        key=key,
        canonical_producer=(
            "PpapMetricsService.get_rolling_duration_curve_value"
            if hist
            else "PpapMetricsService.get_duration_curve_value"
        ),
        canonical_unit="m/s",
        display_unit="km/h",
        display_multiplier=MPS_TO_KMH,
        temporal_semantics="rolling_best" if hist else "snapshot",
        native_cadence_days=1 if hist else 7,
        aggregation_type="rolling_best" if hist else "best_effort",
        smoothing_window_days=ROLLING_CURVE_LOOKBACK_DAYS if hist else None,
        direction="higher_is_better",
        supports_as_of=True,
        supports_trend=True,
        supports_period_comparison=True,
        source_type="computed",
        dependencies=("running.best_efforts",),
        period_summary="latest_snapshot" if hist else "best",
        meaningful_change_fallback_relative_pct=1.5,
        meaningful_change_minimum_absolute=0.15,
        lookback_days=ROLLING_CURVE_LOOKBACK_DAYS if hist else None,
    )


def _build_contracts() -> Dict[str, TemporalMetricContract]:
    contracts: Dict[str, TemporalMetricContract] = {
        "fitness.ctl": _c(
            key="fitness.ctl",
            canonical_producer="PpapMetricsService.get_ctl",
            canonical_unit="tss",
            display_unit="load",
            display_multiplier=1.0,
            temporal_semantics="derived_state",
            native_cadence_days=1,
            aggregation_type="ema",
            smoothing_window_days=42,
            direction="context",
            supports_as_of=True,
            supports_trend=True,
            supports_period_comparison=True,
            source_type="computed",
            dependencies=("daily_tss",),
            period_summary="end_and_mean",
            meaningful_change_fallback_relative_pct=5.0,
            meaningful_change_minimum_absolute=2.0,
        ),
        "fitness.atl": _c(
            key="fitness.atl",
            canonical_producer="PpapMetricsService.get_atl",
            canonical_unit="tss",
            display_unit="load",
            display_multiplier=1.0,
            temporal_semantics="derived_state",
            native_cadence_days=1,
            aggregation_type="ema",
            smoothing_window_days=7,
            direction="context",
            supports_as_of=True,
            supports_trend=True,
            supports_period_comparison=True,
            source_type="computed",
            dependencies=("daily_tss",),
            period_summary="end_and_mean",
            meaningful_change_fallback_relative_pct=8.0,
            meaningful_change_minimum_absolute=3.0,
        ),
        "fitness.tsb": _c(
            key="fitness.tsb",
            canonical_producer="PpapMetricsService.get_tsb",
            canonical_unit="tss",
            display_unit="load",
            display_multiplier=1.0,
            temporal_semantics="derived_state",
            native_cadence_days=1,
            aggregation_type="difference",
            smoothing_window_days=7,
            direction="context",
            supports_as_of=True,
            supports_trend=True,
            supports_period_comparison=True,
            source_type="computed",
            dependencies=("fitness.ctl", "fitness.atl"),
            period_summary="end_and_mean",
            meaningful_change_fallback_relative_pct=15.0,
            meaningful_change_minimum_absolute=5.0,
        ),
        "fitness.form": _c(
            key="fitness.form",
            canonical_producer="PpapMetricsService.get_tsb",
            canonical_unit="tss",
            display_unit="load",
            display_multiplier=1.0,
            temporal_semantics="derived_state",
            native_cadence_days=1,
            aggregation_type="difference",
            smoothing_window_days=7,
            direction="context",
            supports_as_of=True,
            supports_trend=True,
            supports_period_comparison=True,
            source_type="computed",
            dependencies=("fitness.tsb",),
            period_summary="end_and_mean",
            meaningful_change_fallback_relative_pct=15.0,
            meaningful_change_minimum_absolute=5.0,
        ),
        "fitness.ef_30d": _c(
            key="fitness.ef_30d",
            canonical_producer="PpapMetricsService.get_ef_rolling",
            canonical_unit="m/s/bpm",
            display_unit="m_per_s_per_bpm",
            display_multiplier=1.0,
            temporal_semantics="rolling_median",
            native_cadence_days=1,
            aggregation_type="rolling_median",
            smoothing_window_days=30,
            direction="higher_is_better",
            supports_as_of=True,
            supports_trend=True,
            supports_period_comparison=True,
            source_type="computed",
            period_summary="median",
            meaningful_change_fallback_relative_pct=2.0,
            meaningful_change_minimum_absolute=0.02,
        ),
        "fitness.ef_60d": _c(
            key="fitness.ef_60d",
            canonical_producer="PpapMetricsService.get_ef_rolling",
            canonical_unit="m/s/bpm",
            display_unit="m_per_s_per_bpm",
            display_multiplier=1.0,
            temporal_semantics="rolling_median",
            native_cadence_days=1,
            aggregation_type="rolling_median",
            smoothing_window_days=60,
            direction="higher_is_better",
            supports_as_of=True,
            supports_trend=True,
            supports_period_comparison=True,
            source_type="computed",
            period_summary="median",
            meaningful_change_fallback_relative_pct=2.0,
            meaningful_change_minimum_absolute=0.02,
        ),
        "fitness.ef_90d": _c(
            key="fitness.ef_90d",
            canonical_producer="PpapMetricsService.get_ef_rolling",
            canonical_unit="m/s/bpm",
            display_unit="m_per_s_per_bpm",
            display_multiplier=1.0,
            temporal_semantics="rolling_median",
            native_cadence_days=1,
            aggregation_type="rolling_median",
            smoothing_window_days=90,
            direction="higher_is_better",
            supports_as_of=True,
            supports_trend=True,
            supports_period_comparison=True,
            source_type="computed",
            period_summary="median",
            meaningful_change_fallback_relative_pct=2.0,
            meaningful_change_minimum_absolute=0.02,
        ),
        "cardio.hrv_7d": _c(
            key="cardio.hrv_7d",
            canonical_producer="McpDerivedMetricsService._hrv_rolling",
            canonical_unit="ms",
            display_unit="ms",
            display_multiplier=1.0,
            temporal_semantics="rolling_mean",
            native_cadence_days=1,
            aggregation_type="rolling_mean",
            smoothing_window_days=7,
            direction="higher_is_better",
            supports_as_of=True,
            supports_trend=True,
            supports_period_comparison=True,
            source_type="measured",
            period_summary="median",
            meaningful_change_fallback_relative_pct=8.0,
            meaningful_change_minimum_absolute=3.0,
        ),
        "cardio.rhr_7d": _c(
            key="cardio.rhr_7d",
            canonical_producer="PpapMetricsService.get_rhr_rolling",
            canonical_unit="bpm",
            display_unit="bpm",
            display_multiplier=1.0,
            temporal_semantics="rolling_mean",
            native_cadence_days=1,
            aggregation_type="rolling_mean",
            smoothing_window_days=7,
            direction="lower_is_better",
            supports_as_of=True,
            supports_trend=True,
            supports_period_comparison=True,
            source_type="measured",
            period_summary="median",
            meaningful_change_fallback_relative_pct=3.0,
            meaningful_change_minimum_absolute=1.0,
        ),
        "recovery.hrv_delta_pct": _c(
            key="recovery.hrv_delta_pct",
            canonical_producer="PpapMetricsService.get_hrv_delta_pct",
            canonical_unit="pct",
            display_unit="%",
            display_multiplier=1.0,
            temporal_semantics="observation",
            native_cadence_days=1,
            aggregation_type="point",
            smoothing_window_days=None,
            direction="higher_is_better",
            supports_as_of=True,
            supports_trend=True,
            supports_period_comparison=True,
            source_type="computed",
            dependencies=("cardio.hrv_7d", "recovery.hrv_baseline"),
            period_summary="median",
            meaningful_change_fallback_relative_pct=20.0,
            meaningful_change_minimum_absolute=3.0,
        ),
        "running.critical_speed": _c(
            key="running.critical_speed",
            canonical_producer="PerformanceMetricsService.calculate_critical_speed",
            canonical_unit="m/s",
            display_unit="km/h",
            display_multiplier=MPS_TO_KMH,
            temporal_semantics="snapshot",
            native_cadence_days=7,
            aggregation_type="linear_fit",
            smoothing_window_days=None,
            direction="higher_is_better",
            supports_as_of=True,
            supports_trend=True,
            supports_period_comparison=True,
            source_type="computed",
            dependencies=("running.best_efforts",),
            period_summary="latest_snapshot",
            meaningful_change_fallback_relative_pct=1.0,
            meaningful_change_minimum_absolute=0.1,
            lookback_days=ROLLING_CURVE_LOOKBACK_DAYS,
        ),
        "running.critical_power": _c(
            key="running.critical_power",
            canonical_producer="PpapMetricsService.get_critical_power_snapshot",
            canonical_unit="W",
            display_unit="W",
            display_multiplier=1.0,
            temporal_semantics="snapshot",
            native_cadence_days=7,
            aggregation_type="linear_fit",
            smoothing_window_days=None,
            direction="higher_is_better",
            supports_as_of=True,
            supports_trend=True,
            supports_period_comparison=True,
            source_type="computed",
            period_summary="latest_snapshot",
            meaningful_change_fallback_relative_pct=2.0,
            meaningful_change_minimum_absolute=5.0,
        ),
        "running.durability_score": _c(
            key="running.durability_score",
            canonical_producer="CoachingDecisionMetricsService.get_durability_score",
            canonical_unit="score",
            display_unit="score",
            display_multiplier=1.0,
            temporal_semantics="snapshot",
            native_cadence_days=7,
            aggregation_type="score",
            smoothing_window_days=28,
            direction="higher_is_better",
            supports_as_of=True,
            supports_trend=True,
            supports_period_comparison=True,
            source_type="computed",
            period_summary="median",
            meaningful_change_fallback_relative_pct=5.0,
            meaningful_change_minimum_absolute=3.0,
        ),
        "performance.vo2max": _c(
            key="performance.vo2max",
            canonical_producer="GarminPerformanceMetric.vo2_max_precise",
            canonical_unit="ml/kg/min",
            display_unit="ml/kg/min",
            display_multiplier=1.0,
            temporal_semantics="observation",
            native_cadence_days=7,
            aggregation_type="point",
            smoothing_window_days=None,
            direction="higher_is_better",
            supports_as_of=True,
            supports_trend=True,
            supports_period_comparison=True,
            source_type="measured",
            period_summary="latest_snapshot",
            meaningful_change_fallback_relative_pct=1.5,
            meaningful_change_minimum_absolute=0.5,
        ),
        "recovery.sleep_score": _c(
            key="recovery.sleep_score",
            canonical_producer="Sleep.overall_score",
            canonical_unit="score",
            display_unit="score",
            display_multiplier=1.0,
            temporal_semantics="observation",
            native_cadence_days=1,
            aggregation_type="point",
            smoothing_window_days=None,
            direction="higher_is_better",
            supports_as_of=True,
            supports_trend=True,
            supports_period_comparison=True,
            source_type="measured",
            period_summary="median",
            meaningful_change_fallback_relative_pct=5.0,
            meaningful_change_minimum_absolute=3.0,
        ),
        "performance.threshold_pace": _c(
            key="performance.threshold_pace",
            canonical_producer="LactateThresholdHistory.lactate_threshold_speed",
            canonical_unit="sec/km",
            display_unit="sec/km",
            display_multiplier=1.0,
            temporal_semantics="observation",
            native_cadence_days=7,
            aggregation_type="point",
            smoothing_window_days=None,
            direction="lower_is_better",
            supports_as_of=True,
            supports_trend=True,
            supports_period_comparison=True,
            source_type="measured",
            period_summary="latest_snapshot",
            meaningful_change_fallback_relative_pct=1.5,
            meaningful_change_minimum_absolute=3.0,
        ),
        "cardio.drift_score": _c(
            key="cardio.drift_score",
            canonical_producer="McpDerivedMetricsService",
            canonical_unit="score",
            display_unit="score",
            display_multiplier=1.0,
            temporal_semantics="rolling_median",
            native_cadence_days=1,
            aggregation_type="rolling_median",
            smoothing_window_days=28,
            direction="lower_is_better",
            supports_as_of=True,
            supports_trend=True,
            supports_period_comparison=True,
            source_type="computed",
            period_summary="median",
            meaningful_change_fallback_relative_pct=10.0,
            meaningful_change_minimum_absolute=1.0,
        ),
        "fitness.gain_rate": _c(
            key="fitness.gain_rate",
            canonical_producer="derived_ctl_delta",
            canonical_unit="load/day",
            display_unit="load_per_day",
            display_multiplier=1.0,
            temporal_semantics="derived_state",
            native_cadence_days=1,
            aggregation_type="difference",
            smoothing_window_days=28,
            direction="context",
            supports_as_of=True,
            supports_trend=True,
            supports_period_comparison=True,
            source_type="computed",
            dependencies=("fitness.ctl",),
            period_summary="mean",
            meaningful_change_fallback_relative_pct=20.0,
            meaningful_change_minimum_absolute=0.2,
        ),
        "load.monotony": _c(
            key="load.monotony",
            canonical_producer="load_variability",
            canonical_unit="ratio",
            display_unit="ratio",
            display_multiplier=1.0,
            temporal_semantics="rolling_mean",
            native_cadence_days=1,
            aggregation_type="rolling_mean",
            smoothing_window_days=7,
            direction="lower_is_better",
            supports_as_of=True,
            supports_trend=True,
            supports_period_comparison=True,
            source_type="computed",
            period_summary="median",
            meaningful_change_fallback_relative_pct=10.0,
            meaningful_change_minimum_absolute=0.1,
        ),
        "load.strain": _c(
            key="load.strain",
            canonical_producer="load_variability",
            canonical_unit="score",
            display_unit="score",
            display_multiplier=1.0,
            temporal_semantics="rolling_mean",
            native_cadence_days=1,
            aggregation_type="product",
            smoothing_window_days=7,
            direction="context",
            supports_as_of=True,
            supports_trend=True,
            supports_period_comparison=True,
            source_type="computed",
            dependencies=("load.monotony",),
            period_summary="median",
            meaningful_change_fallback_relative_pct=15.0,
            meaningful_change_minimum_absolute=20.0,
        ),
        "coaching.zone1_pct": _zone("coaching.zone1_pct"),
        "coaching.zone2_pct": _zone("coaching.zone2_pct"),
        "coaching.zone3_pct": _zone("coaching.zone3_pct"),
        "coaching.polarization_score": _c(
            key="coaching.polarization_score",
            canonical_producer="CoachingAnalysisService",
            canonical_unit="score",
            display_unit="score",
            display_multiplier=1.0,
            temporal_semantics="rolling_mean",
            native_cadence_days=1,
            aggregation_type="rolling",
            smoothing_window_days=28,
            direction="context",
            supports_as_of=True,
            supports_trend=True,
            supports_period_comparison=True,
            source_type="computed",
            dependencies=("coaching.zone1_pct", "coaching.zone3_pct"),
            period_summary="median",
            meaningful_change_fallback_relative_pct=8.0,
            meaningful_change_minimum_absolute=3.0,
        ),
        "consistency.score": _c(
            key="consistency.score",
            canonical_producer="consistency",
            canonical_unit="score",
            display_unit="score",
            display_multiplier=1.0,
            temporal_semantics="rolling_mean",
            native_cadence_days=1,
            aggregation_type="rolling",
            smoothing_window_days=28,
            direction="higher_is_better",
            supports_as_of=True,
            supports_trend=True,
            supports_period_comparison=True,
            source_type="computed",
            period_summary="median",
            meaningful_change_fallback_relative_pct=8.0,
            meaningful_change_minimum_absolute=3.0,
        ),
        "readiness.total_score": _readiness("readiness.total_score"),
        "readiness.sleep_component": _readiness("readiness.sleep_component"),
        "readiness.hrv_component": _readiness("readiness.hrv_component"),
        "readiness.form_component": _readiness("readiness.form_component"),
        "sleep.sleep_debt_7d": _c(
            key="sleep.sleep_debt_7d",
            canonical_producer="PpapMetricsService.get_sleep_debt_hours",
            canonical_unit="hours",
            display_unit="hours",
            display_multiplier=1.0,
            temporal_semantics="rolling_mean",
            native_cadence_days=1,
            aggregation_type="sum",
            smoothing_window_days=7,
            direction="lower_is_better",
            supports_as_of=True,
            supports_trend=True,
            supports_period_comparison=True,
            source_type="measured",
            period_summary="median",
            meaningful_change_fallback_relative_pct=20.0,
            meaningful_change_minimum_absolute=1.0,
        ),
        "stimulus.easy_minutes_7d": _stimulus("stimulus.easy_minutes_7d", "easy_volume", 7),
        "stimulus.easy_minutes_28d": _stimulus("stimulus.easy_minutes_28d", "easy_volume", 28),
        "stimulus.threshold_minutes_14d": _stimulus(
            "stimulus.threshold_minutes_14d", "threshold_volume", 14
        ),
        "stimulus.vo2_minutes_14d": _stimulus(
            "stimulus.vo2_minutes_14d",
            "vo2_volume",
            14,
            producer="TrainingResponseService.vo2_interval_minutes",
        ),
        "stimulus.long_run_minutes_28d": _stimulus(
            "stimulus.long_run_minutes_28d",
            "long_run_volume",
            28,
            producer="TrainingResponseService.long_aerobic_minutes",
        ),
        "stimulus.tss_7d": _stimulus("stimulus.tss_7d", "weekly_tss", 7, unit="tss"),
        "stimulus.tss_28d": _stimulus("stimulus.tss_28d", "weekly_tss", 28, unit="tss"),
    }
    for key, (metric_type, _duration) in DURATION_CURVE_METRICS.items():
        if metric_type != "speed":
            continue
        contracts[key] = _speed_contract(key, hist=False)
        contracts[f"{key}_hist"] = _speed_contract(f"{key}_hist", hist=True)
    return contracts


def _zone(key: str) -> TemporalMetricContract:
    return _c(
        key=key,
        canonical_producer="PpapMetricsService.get_coaching_zone_pct",
        canonical_unit="%",
        display_unit="%",
        display_multiplier=1.0,
        temporal_semantics="rolling_mean",
        native_cadence_days=1,
        aggregation_type="rolling_share",
        smoothing_window_days=28,
        direction="context",
        supports_as_of=True,
        supports_trend=True,
        supports_period_comparison=True,
        source_type="computed",
        period_summary="median",
        meaningful_change_fallback_relative_pct=8.0,
        meaningful_change_minimum_absolute=3.0,
    )


def _readiness(key: str) -> TemporalMetricContract:
    return _c(
        key=key,
        canonical_producer="TrainingReadinessService.calculate_training_readiness",
        canonical_unit="score",
        display_unit="score",
        display_multiplier=1.0,
        temporal_semantics="snapshot",
        native_cadence_days=1,
        aggregation_type="score",
        smoothing_window_days=None,
        direction="higher_is_better",
        supports_as_of=True,
        supports_trend=True,
        supports_period_comparison=True,
        source_type="computed",
        period_summary="median",
        meaningful_change_fallback_relative_pct=8.0,
        meaningful_change_minimum_absolute=4.0,
    )


def _stimulus(
    key: str,
    kind: str,
    window: int,
    *,
    producer: str = "TrainingResponseService._stimulus_value",
    unit: str = "min",
) -> TemporalMetricContract:
    return _c(
        key=key,
        canonical_producer=producer,
        canonical_unit=unit,
        display_unit=unit,
        display_multiplier=1.0,
        temporal_semantics="cumulative",
        native_cadence_days=7,
        aggregation_type="sum",
        smoothing_window_days=window,
        direction="context",
        supports_as_of=True,
        supports_trend=True,
        supports_period_comparison=True,
        source_type="computed",
        dependencies=(kind,),
        period_summary="sum",
        meaningful_change_fallback_relative_pct=15.0,
        meaningful_change_minimum_absolute=10.0,
        aggregation_window_days=window,
    )


TEMPORAL_CONTRACTS: Dict[str, TemporalMetricContract] = _build_contracts()

# Short training-response ids → aggregation window owned by metric metadata.
STIMULUS_AGGREGATION_DAYS: Dict[str, int] = {
    "easy_volume": 28,
    "threshold_volume": 14,
    "vo2_volume": 14,
    "long_run_volume": 28,
    "high_intensity_volume": 14,
    "weekly_tss": 7,
    "tss_7d": 7,
    "tss_28d": 28,
}

TREND_METRIC_KEYS: Dict[str, str] = {
    "vo2max": "performance.vo2max",
    "critical_speed": "running.critical_speed",
    "easy_run_efficiency": "fitness.ef_30d",
    "hr_drift": "cardio.drift_score",
    "decoupling": "cardio.drift_score",
    "ctl": "fitness.ctl",
    "resting_hr": "cardio.rhr_7d",
    "hrv_rmssd": "cardio.hrv_7d",
    "sleep_score": "recovery.sleep_score",
    "durability": "running.durability_score",
    "lactate_threshold_pace": "performance.threshold_pace",
}


def contract_for(key: str) -> Optional[TemporalMetricContract]:
    return TEMPORAL_CONTRACTS.get(key)


def contract_for_trend(metric: str) -> Optional[TemporalMetricContract]:
    return TEMPORAL_CONTRACTS.get(TREND_METRIC_KEYS.get(metric, metric))


def aggregation_window_days(stimulus: str, explicit: Optional[int] = None) -> int:
    if explicit is not None and explicit > 0:
        return int(explicit)
    if stimulus in TEMPORAL_CONTRACTS and TEMPORAL_CONTRACTS[stimulus].aggregation_window_days:
        return int(TEMPORAL_CONTRACTS[stimulus].aggregation_window_days or 7)
    return int(STIMULUS_AGGREGATION_DAYS.get(stimulus, 7))


def stimulus_bounds(
    outcome_date: date,
    lag_days: int,
    *,
    aggregation_days: int,
) -> Dict[str, Any]:
    """Stimulus ends `lag_days` before the outcome and lasts `aggregation_days`.

    Window length does not grow with lag, and the outcome day is excluded when lag > 0.
    """
    window = max(1, int(aggregation_days))
    lag = max(0, int(lag_days))
    stimulus_end = outcome_date - timedelta(days=lag)
    stimulus_start = stimulus_end - timedelta(days=window - 1)
    return {
        "outcome_date": outcome_date.isoformat(),
        "lag_days": lag,
        "aggregation_days": window,
        "stimulus_start": stimulus_start,
        "stimulus_end": stimulus_end,
    }


def speed_mps_to_kmh(speed_mps: Optional[float]) -> Optional[float]:
    if speed_mps is None:
        return None
    return round(float(speed_mps) * MPS_TO_KMH, 4)


def present_value(metric_key: str, raw: Optional[float]) -> Optional[float]:
    """Convert a producer value into the canonical display unit."""
    if raw is None:
        return None
    contract = contract_for(metric_key)
    if contract is None or contract.display_multiplier == 1.0:
        return raw
    return round(float(raw) * contract.display_multiplier, 4)


def overlay_contract(payload: Dict[str, Any]) -> Dict[str, Any]:
    contract = contract_for(str(payload.get("key") or ""))
    if contract is None:
        return payload
    merged = dict(payload)
    public = contract.public_dict()
    for field in (
        "canonical_producer",
        "canonical_unit",
        "display_unit",
        "display_multiplier",
        "temporal_semantics",
        "native_cadence_days",
        "aggregation_type",
        "smoothing_window_days",
        "supports_as_of",
        "period_summary",
        "aggregation_window_days",
        "lookback_days",
        "show_gaps",
        "meaningful_change",
    ):
        merged[field] = public[field]
    merged["unit"] = contract.display_unit
    if contract.direction != "context":
        merged["direction"] = contract.direction
    return merged


def effective_sample_count(
    raw_sample_count: int,
    *,
    span_days: int,
    smoothing_window_days: Optional[int],
) -> int:
    """Conservative heuristic. Not an exact effective-sample-size estimator.

    Rolling points closer than the smoothing window are not independent, so
    effective_n is capped by temporal_span / smoothing_window.
    """
    raw = max(0, int(raw_sample_count))
    if raw == 0:
        return 0
    window = int(smoothing_window_days or 1)
    if window <= 1:
        return raw
    span = max(int(span_days), 1)
    cap = max(1, int(math.floor(span / window)))
    return min(raw, cap)


def _mad(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    mid = median(values)
    deviations = [abs(float(v) - mid) for v in values]
    return float(median(deviations)) if deviations else 0.0


def personal_noise_threshold(
    series: Sequence[Tuple[date, float]],
    contract: Optional[TemporalMetricContract],
    *,
    baseline: Optional[float],
) -> Dict[str, Any]:
    """Week-to-week MAD when possible, otherwise a metric-specific fallback."""
    fallback_pct = 5.0
    minimum_absolute = 0.0
    if contract is not None:
        fallback_pct = contract.meaningful_change_fallback_relative_pct
        minimum_absolute = contract.meaningful_change_minimum_absolute
    weekly: List[float] = []
    if len(series) >= 2:
        for (day_a, val_a), (day_b, val_b) in zip(series, series[1:]):
            gap = abs((day_b - day_a).days)
            if 5 <= gap <= 10:
                weekly.append(val_b - val_a)
        if len(weekly) < 3:
            weekly = [series[i][1] - series[i - 1][1] for i in range(1, len(series))]
    mad = _mad(weekly) if weekly else 0.0
    # 1.4826 * MAD approximates sigma for a normal distribution, but we treat
    # the result as a heuristic noise floor, not a formal standard error.
    robust = 1.4826 * mad
    relative_floor = 0.0
    if baseline not in (None, 0):
        relative_floor = abs(float(baseline)) * (fallback_pct / 100.0)
    threshold = max(minimum_absolute, robust, relative_floor)
    method = "personal_variability" if mad > 0 else "fallback_relative_pct"
    return {
        "method": method,
        "threshold_absolute": round(threshold, 4),
        "mad": round(mad, 4),
        "fallback_relative_pct": fallback_pct,
        "minimum_absolute": minimum_absolute,
        "heuristic": True,
    }


def sample_overlap(raw_pairs: int, *, aggregation_days: int, step_days: int = 7) -> Dict[str, Any]:
    window = max(1, int(aggregation_days))
    step = max(1, int(step_days))
    if raw_pairs <= 1 or window <= step:
        level = "low"
        effective = raw_pairs
    else:
        ratio = 1.0 - (step / window)
        level = "high" if ratio >= 0.5 else "moderate"
        effective = max(1, int(round(raw_pairs * (step / window))))
        effective = min(raw_pairs, effective)
    return {
        "raw_pairs": raw_pairs,
        "effective_pairs": effective,
        "sample_overlap": level,
        "note": "Overlapping windows are not independent observations.",
    }


def percentile_rank(current: float, history: Sequence[float]) -> Optional[float]:
    values = [float(v) for v in history if v is not None]
    if len(values) < 3:
        return None
    below = sum(1 for v in values if v <= current)
    return round(100.0 * below / len(values), 1)
