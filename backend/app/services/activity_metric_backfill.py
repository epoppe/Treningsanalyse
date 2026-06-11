"""Utledning og backfill av manglende aktivitetsfelter fra lokale kilder."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from ..database.models.activity import Activity
from ..utils.speed_pace import (
    aggregate_speed_pace_from_totals,
    mps_to_pace_sec_per_km,
)
from .activity_field_extraction import extract_activity_list_fields
from .health_metric_backfill import apply_activity_vo2_precise_backfill

# Pace: ca. 1:30/km (sprint) til 60:00/km (gang)
MIN_PACE_SEC_PER_KM = 90.0
MAX_PACE_SEC_PER_KM = 3600.0
MIN_DISTANCE_M_FOR_PACE = 100.0
MIN_DURATION_S_FOR_PACE = 60.0

# Kadens i spm (løp)
MIN_RUNNING_CADENCE_SPM = 40.0
MAX_RUNNING_CADENCE_SPM = 250.0
FIT_CADENCE_DOUBLE_THRESHOLD = 120.0

# Høyde fra FIT
MIN_ALTITUDE_SAMPLES = 10
MIN_ELEVATION_M = -500.0
MAX_ELEVATION_M = 9000.0

# Varighet fra FIT
MIN_DURATION_SAMPLES = 5
MOVING_SPEED_THRESHOLD_MPS = 0.3
MAX_RECORD_GAP_S = 30.0

# Steg fra FIT step_length (mm)
MIN_STEP_LENGTH_MM = 200.0
MAX_STEP_LENGTH_MM = 2000.0


@dataclass
class ActivityBackfillResult:
    changed: bool = False
    fixes: List[str] = field(default_factory=list)


def _coerce_positive_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric <= 0:
        return None
    return numeric


def _coerce_positive_int(value: Any) -> Optional[int]:
    numeric = _coerce_positive_float(value)
    if numeric is None:
        return None
    return int(round(numeric))


def _pace_in_plausible_range(pace_sec: float) -> bool:
    return MIN_PACE_SEC_PER_KM <= pace_sec <= MAX_PACE_SEC_PER_KM


def normalize_garmin_average_pace(raw: Any) -> Optional[float]:
    """
    Garmin activitylist/summary lagrer averagePace som min/km (f.eks. 6.22).
    Internt lagres pace som sek/km.
    """
    value = _coerce_positive_float(raw)
    if value is None:
        return None
    if value <= 30.0:
        pace_sec = value * 60.0
    else:
        pace_sec = value
    if not _pace_in_plausible_range(pace_sec):
        return None
    return round(pace_sec, 1)


def derive_average_pace_sec_per_km(
    *,
    average_pace: Optional[float] = None,
    average_speed: Optional[float] = None,
    distance_m: Optional[float] = None,
    duration_s: Optional[float] = None,
) -> Optional[float]:
    """Robust utledning av average_pace (s/km) fra eksisterende felter."""
    normalized = normalize_garmin_average_pace(average_pace)
    if normalized is not None:
        return normalized

    speed = _coerce_positive_float(average_speed)
    if speed is not None:
        pace = mps_to_pace_sec_per_km(speed)
        if pace is not None and _pace_in_plausible_range(pace):
            return pace

    dist = _coerce_positive_float(distance_m)
    dur = _coerce_positive_float(duration_s)
    if dist is not None and dur is not None and dist >= MIN_DISTANCE_M_FOR_PACE and dur >= MIN_DURATION_S_FOR_PACE:
        _, pace = aggregate_speed_pace_from_totals(dist, dur)
        if pace is not None and _pace_in_plausible_range(pace):
            return round(float(pace), 1)
    return None


def scale_fit_cadence_to_running_spm(
    fit_max: float,
    average_running_cadence: Optional[float] = None,
) -> Optional[float]:
    """FIT-kadens er ofte én fot; skaler til løps-kadens (spm) når det er tryggere."""
    if fit_max <= 0:
        return None
    candidates = [fit_max]
    if fit_max <= FIT_CADENCE_DOUBLE_THRESHOLD:
        candidates.append(fit_max * 2.0)
    if average_running_cadence is not None and average_running_cadence > 0:
        return min(
            candidates,
            key=lambda value: abs(value - float(average_running_cadence)),
        )
    return max(candidates)


def extract_fit_max_running_cadence(
    details_df: pd.DataFrame,
    average_running_cadence: Optional[float] = None,
) -> Optional[float]:
    if details_df is None or details_df.empty or "cadence" not in details_df.columns:
        return None
    series = pd.to_numeric(details_df["cadence"], errors="coerce").dropna()
    series = series[series > 0]
    if series.empty:
        return None
    fit_max = float(series.max())
    spm = scale_fit_cadence_to_running_spm(fit_max, average_running_cadence)
    if spm is None or not (MIN_RUNNING_CADENCE_SPM <= spm <= MAX_RUNNING_CADENCE_SPM):
        return None
    return round(spm, 1)


def extract_fit_elevation_bounds(
    details_df: pd.DataFrame,
    *,
    min_samples: int = MIN_ALTITUDE_SAMPLES,
) -> Tuple[Optional[float], Optional[float]]:
    if details_df is None or details_df.empty or "altitude" not in details_df.columns:
        return None, None
    series = pd.to_numeric(details_df["altitude"], errors="coerce").dropna()
    if len(series) < min_samples:
        return None, None
    min_elev = float(series.min())
    max_elev = float(series.max())
    if not (MIN_ELEVATION_M <= min_elev <= MAX_ELEVATION_M):
        return None, None
    if not (MIN_ELEVATION_M <= max_elev <= MAX_ELEVATION_M):
        return None, None
    if max_elev < min_elev:
        return None, None
    return round(min_elev, 1), round(max_elev, 1)


def extract_fit_durations(
    details_df: pd.DataFrame,
    *,
    moving_speed_threshold_mps: float = MOVING_SPEED_THRESHOLD_MPS,
) -> Tuple[Optional[float], Optional[float]]:
    """Utled elapsed/moving varighet fra FIT/parquet tidsstempler og fart."""
    if details_df is None or details_df.empty or "timestamp" not in details_df.columns:
        return None, None
    frame = details_df.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    frame = frame.dropna(subset=["timestamp"]).sort_values("timestamp")
    if len(frame) < MIN_DURATION_SAMPLES:
        return None, None

    elapsed = (frame["timestamp"].iloc[-1] - frame["timestamp"].iloc[0]).total_seconds()
    if elapsed <= 0:
        return None, None

    moving = None
    if "speed" in frame.columns:
        speeds = pd.to_numeric(frame["speed"], errors="coerce")
        dt = frame["timestamp"].diff().dt.total_seconds().fillna(0.0).clip(lower=0.0, upper=MAX_RECORD_GAP_S)
        moving = float(dt[speeds.fillna(0.0) >= moving_speed_threshold_mps].sum())
        if moving <= 0:
            moving = None

    return round(elapsed, 1), round(moving, 1) if moving is not None else None


def derive_total_steps(
    *,
    distance_m: Optional[float] = None,
    stride_length_m: Optional[float] = None,
    average_speed_mps: Optional[float] = None,
    average_running_cadence_spm: Optional[float] = None,
) -> Optional[int]:
    """Estimer total_steps fra distanse og steglengde når eksplisitte steg mangler."""
    distance = _coerce_positive_float(distance_m)
    if distance is None or distance < MIN_DISTANCE_M_FOR_PACE:
        return None

    stride = _coerce_positive_float(stride_length_m)
    if stride is not None and 0.3 <= stride <= 2.5:
        return int(round(distance / stride))

    speed = _coerce_positive_float(average_speed_mps)
    cadence = _coerce_positive_float(average_running_cadence_spm)
    if speed is not None and cadence is not None and cadence > 0:
        stride_from_cadence = (speed * 60.0) / cadence
        if 0.3 <= stride_from_cadence <= 2.5:
            return int(round(distance / stride_from_cadence))
    return None


def extract_fit_total_steps(
    details_df: pd.DataFrame,
    *,
    detailed_metrics: Optional[dict] = None,
) -> Optional[int]:
    """Estimer total_steps fra siste FIT-distanse og typisk steglengde (mm)."""
    if details_df is not None and not details_df.empty and "step_length" in details_df.columns:
        steps = _extract_total_steps_from_frame(details_df)
        if steps is not None:
            return steps

    if detailed_metrics and isinstance(detailed_metrics.get("records"), list):
        records = detailed_metrics["records"]
        if records:
            frame = pd.DataFrame(records)
            steps = _extract_total_steps_from_frame(frame)
            if steps is not None:
                return steps
    return None


def _extract_total_steps_from_frame(details_df: pd.DataFrame) -> Optional[int]:
    if details_df is None or details_df.empty:
        return None
    if "distance" not in details_df.columns or "step_length" not in details_df.columns:
        return None

    distances = pd.to_numeric(details_df["distance"], errors="coerce").dropna()
    step_lengths = pd.to_numeric(details_df["step_length"], errors="coerce").dropna()
    if distances.empty or step_lengths.empty:
        return None

    final_distance_m = float(distances.iloc[-1])
    if final_distance_m < MIN_DISTANCE_M_FOR_PACE:
        return None

    valid_steps = step_lengths[
        (step_lengths >= MIN_STEP_LENGTH_MM) & (step_lengths <= MAX_STEP_LENGTH_MM)
    ]
    if valid_steps.empty:
        return None

    median_step_mm = float(valid_steps.median())
    step_m = median_step_mm / 1000.0
    steps = int(round(final_distance_m / step_m))
    if steps <= 0:
        return None
    return steps


def _get_fit_details(storage: Any, activity_id: str | int) -> Optional[pd.DataFrame]:
    if storage is None:
        return None
    try:
        return storage.get_activity_details(int(activity_id))
    except (TypeError, ValueError):
        return None


def apply_activity_field_backfill(
    activity: Activity,
    *,
    storage: Any = None,
    garmin_list: Optional[Dict[str, Any]] = None,
    db: Any = None,
) -> ActivityBackfillResult:
    """
    Fyll manglende aktivitetsfelter fra Garmin-liste (hvis gitt), FIT/parquet og avledning.
    Skriver kun når grunnlaget er tydelig — hopper over tvilsomme verdier.
    """
    result = ActivityBackfillResult()
    details_df = _get_fit_details(storage, activity.activity_id)

    if garmin_list:
        list_fields = extract_activity_list_fields(garmin_list)
        for attr, value in list_fields.items():
            if value is None or getattr(activity, attr, None) is not None:
                continue
            setattr(activity, attr, value)
            result.changed = True
            result.fixes.append(f"{attr} fra Garmin-liste")

        max_cadence = _coerce_positive_float(
            garmin_list.get("maxRunningCadenceInStepsPerMinute")
            or garmin_list.get("maxRunningCadence")
        )
        if activity.max_running_cadence is None and max_cadence is not None:
            if MIN_RUNNING_CADENCE_SPM <= max_cadence <= MAX_RUNNING_CADENCE_SPM:
                activity.max_running_cadence = round(max_cadence, 1)
                result.changed = True
                result.fixes.append(f"max_running_cadence fra Garmin-liste: {activity.max_running_cadence}")

        garmin_pace = normalize_garmin_average_pace(garmin_list.get("averagePace"))
        if activity.average_pace is None and garmin_pace is not None:
            activity.average_pace = garmin_pace
            result.changed = True
            result.fixes.append(f"average_pace fra Garmin-liste: {garmin_pace:.1f} s/km")

    if activity.average_pace is None:
        pace = derive_average_pace_sec_per_km(
            average_pace=activity.average_pace,
            average_speed=activity.average_speed,
            distance_m=activity.distance,
            duration_s=activity.duration,
        )
        if pace is not None:
            activity.average_pace = pace
            result.changed = True
            source = "average_speed" if activity.average_speed else "distance/duration"
            result.fixes.append(f"average_pace utledet fra {source}: {pace:.1f} s/km")

    if details_df is not None:
        if activity.max_running_cadence is None:
            max_cadence = extract_fit_max_running_cadence(
                details_df,
                activity.average_running_cadence,
            )
            if max_cadence is not None:
                activity.max_running_cadence = max_cadence
                result.changed = True
                result.fixes.append(f"max_running_cadence fra FIT: {max_cadence}")

        if activity.min_elevation is None or activity.max_elevation is None:
            min_elev, max_elev = extract_fit_elevation_bounds(details_df)
            if activity.min_elevation is None and min_elev is not None:
                activity.min_elevation = min_elev
                result.changed = True
                result.fixes.append(f"min_elevation fra FIT: {min_elev}")
            if activity.max_elevation is None and max_elev is not None:
                activity.max_elevation = max_elev
                result.changed = True
                result.fixes.append(f"max_elevation fra FIT: {max_elev}")

        if activity.elapsed_duration is None or activity.moving_duration is None:
            elapsed, moving = extract_fit_durations(details_df)
            if activity.elapsed_duration is None and elapsed is not None:
                activity.elapsed_duration = elapsed
                result.changed = True
                result.fixes.append(f"elapsed_duration fra FIT: {elapsed}")
            if activity.moving_duration is None and moving is not None:
                activity.moving_duration = moving
                result.changed = True
                result.fixes.append(f"moving_duration fra FIT: {moving}")

        if activity.total_steps is None:
            steps = extract_fit_total_steps(
                details_df,
                detailed_metrics=activity.detailed_metrics,
            )
            if steps is not None:
                activity.total_steps = steps
                result.changed = True
                result.fixes.append(f"total_steps fra FIT: {steps}")

    if activity.total_steps is None:
        steps = derive_total_steps(
            distance_m=activity.distance,
            stride_length_m=activity.stride_length,
            average_speed_mps=activity.average_speed,
            average_running_cadence_spm=activity.average_running_cadence,
        )
        if steps is not None:
            activity.total_steps = steps
            result.changed = True
            result.fixes.append(f"total_steps utledet: {steps}")

    if db is not None:
        vo2_result = apply_activity_vo2_precise_backfill(activity, db)
        if vo2_result.changed:
            result.changed = True
            result.fixes.extend(vo2_result.fixes)

    return result
