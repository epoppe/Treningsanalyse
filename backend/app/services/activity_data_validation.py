"""Validering og normalisering av aktivitetsfelter etter Garmin-synk."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional

import logging

from ..database.models.activity import Activity

logger = logging.getLogger(__name__)

# Typiske intervaller (heuristikk, ikke Garmin-fasit)
_MIN_BPM = 35.0
_MAX_BPM = 230.0
_STRIDE_M_MIN = 0.35
_STRIDE_M_MAX = 2.5
_GCT_MS_MIN = 80.0
_GCT_MS_MAX = 600.0


@dataclass
class ActivityValidationResult:
    changed: bool = False
    warnings: List[str] = field(default_factory=list)
    fixes: List[str] = field(default_factory=list)


def normalize_stride_length_meters(value: Optional[float]) -> Optional[float]:
    """Garmin list/summary bruker ofte cm; MCP forventer meter."""
    if value is None:
        return None
    v = float(value)
    if v <= 0:
        return None
    if v > _STRIDE_M_MAX:
        converted = v / 100.0
        if _STRIDE_M_MIN <= converted <= _STRIDE_M_MAX:
            return round(converted, 4)
    if _STRIDE_M_MIN <= v <= _STRIDE_M_MAX:
        return round(v, 4)
    if v > 3.0:
        converted = v / 100.0
        if _STRIDE_M_MIN <= converted <= _STRIDE_M_MAX:
            return round(converted, 4)
    return None


def normalize_ground_contact_time_ms(value: Optional[float]) -> Optional[float]:
    """Lagrer GCT i millisekunder (Garmin-standard)."""
    if value is None:
        return None
    v = float(value)
    if v <= 0:
        return None
    if v < 2.0:
        converted = v * 1000.0
        if _GCT_MS_MIN <= converted <= _GCT_MS_MAX:
            return round(converted, 2)
    if _GCT_MS_MIN <= v <= _GCT_MS_MAX:
        return round(v, 2)
    return None


def _hr_in_range(value: float) -> bool:
    return _MIN_BPM <= value <= _MAX_BPM


def max_hr_from_fit_records(detailed_metrics: Optional[dict]) -> Optional[float]:
    if not detailed_metrics:
        return None
    records = detailed_metrics.get("records") or []
    hrs = []
    for record in records:
        hr = record.get("heart_rate")
        if hr is None:
            continue
        try:
            hr_f = float(hr)
        except (TypeError, ValueError):
            continue
        if _hr_in_range(hr_f):
            hrs.append(hr_f)
    return round(max(hrs), 1) if hrs else None


def max_hr_from_storage(storage: Any, activity_id: str | int) -> Optional[float]:
    try:
        details = storage.get_activity_details(int(activity_id))
    except Exception:
        return None
    if details is None or getattr(details, "empty", True):
        return None
    col = "heart_rate" if "heart_rate" in getattr(details, "columns", []) else None
    if not col:
        return None
    series = details[col].dropna()
    if series.empty:
        return None
    try:
        peak = float(series.max())
    except (TypeError, ValueError):
        return None
    if _hr_in_range(peak):
        return round(peak, 1)
    return None


def validate_and_repair_activity(
    activity: Activity,
    *,
    storage: Any = None,
) -> ActivityValidationResult:
    """
    Normaliser enheter og reparer åpenbare puls-feil (max < avg).
    """
    result = ActivityValidationResult()

    if activity.stride_length is not None:
        normalized = normalize_stride_length_meters(activity.stride_length)
        if normalized is None and activity.stride_length > 0:
            result.warnings.append(
                f"stride_length utenfor forventet område: {activity.stride_length}"
            )
        elif normalized != activity.stride_length:
            old = activity.stride_length
            activity.stride_length = normalized
            result.changed = True
            result.fixes.append(f"stride_length {old} -> {normalized} m")

    if activity.ground_contact_time is not None:
        normalized_gct = normalize_ground_contact_time_ms(activity.ground_contact_time)
        if normalized_gct is None and activity.ground_contact_time > 0:
            result.warnings.append(
                f"ground_contact_time utenfor forventet område: {activity.ground_contact_time}"
            )
        elif normalized_gct != activity.ground_contact_time:
            old = activity.ground_contact_time
            activity.ground_contact_time = normalized_gct
            result.changed = True
            result.fixes.append(f"ground_contact_time {old} -> {normalized_gct} ms")

    avg = activity.average_heart_rate
    max_hr = activity.max_heart_rate
    if avg is not None and max_hr is not None and max_hr < avg:
        result.warnings.append(f"max_heart_rate ({max_hr}) < average_heart_rate ({avg})")
        replacement = max_hr_from_fit_records(activity.detailed_metrics)
        if replacement is None and storage is not None:
            replacement = max_hr_from_storage(storage, activity.activity_id)
        if replacement is not None and replacement >= avg:
            activity.max_heart_rate = replacement
            result.changed = True
            result.fixes.append(f"max_heart_rate satt fra FIT/parquet: {replacement} bpm")
        else:
            activity.max_heart_rate = None
            result.changed = True
            result.fixes.append("max_heart_rate nullstilt (ugyldig vs snittpuls)")

    if activity.max_heart_rate is None and storage is not None:
        peak = max_hr_from_storage(storage, activity.activity_id)
        if peak is not None and (avg is None or peak >= avg):
            activity.max_heart_rate = peak
            result.changed = True
            result.fixes.append(f"max_heart_rate fylt fra parquet: {peak} bpm")

    if activity.max_heart_rate is not None and not _hr_in_range(float(activity.max_heart_rate)):
        result.warnings.append(f"max_heart_rate utenfor intervall: {activity.max_heart_rate}")
        activity.max_heart_rate = None
        result.changed = True
        result.fixes.append("max_heart_rate nullstilt (utenfor intervall)")

    return result


def apply_garmin_list_hr_fields(activity: Activity, act_data: dict) -> bool:
    """Sett max/min puls fra aktivitetsliste-JSON (maxHR / minHR)."""
    changed = False
    for src, attr in (("maxHR", "max_heart_rate"), ("minHR", "min_heart_rate")):
        raw = act_data.get(src)
        if raw is None:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if not _hr_in_range(value):
            continue
        if getattr(activity, attr) != value:
            setattr(activity, attr, value)
            changed = True
    return changed
