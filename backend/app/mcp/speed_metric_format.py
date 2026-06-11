"""MCP-spesifikk formatering av hastighets- og pace-metrikker."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from ..database.models.lactate_threshold_history import LactateThresholdHistory
from ..utils.speed_pace import (
    PACE_DISPLAY_UNIT,
    aggregate_speed_pace_from_totals,
    build_pace_payload,
    build_speed_pace_payload,
    check_speed_pace_consistency,
    mps_to_kmh,
    mps_to_pace_sec_per_km,
    normalize_lactate_threshold_raw_speed,
    pace_sec_to_display,
    validate_lactate_threshold_speed,
    validate_running_speed_window,
)

# Kolonnenavn som lagrer fart i m/s (brukerrettet MCP-output skal være km/t + pace).
SPEED_MPS_COLUMN_NAMES = frozenset(
    {
        "average_speed",
        "average_moving_speed",
        "avg_speed",
        "best_speed",
        "lactate_threshold_speed",
        "critical_speed",
        "threshold_speed",
    }
)

# Grade-adjusted speed lagres som m/s internt, men eksponeres som pace (M:SS/km) i MCP.
GRADE_ADJUSTED_SPEED_COLUMNS = frozenset({"avg_grade_adjusted_speed"})

GRADE_ADJUSTED_PACE_METRIC_KEYS = frozenset(
    {
        "activity.grade_adjusted_pace_sec_per_km",
        "activity.grade_adjusted_speed_mps",
        "activity.avg_grade_adjusted_speed",
    }
)

PACE_SEC_COLUMN_NAMES = frozenset(
    {
        "average_pace",
        "avg_pace",
        "best_pace",
    }
)

INTERNAL_SPEED_COLUMN_NAMES = frozenset(
    {
        "raw_lactate_threshold_speed",
    }
)

EXCLUDED_SPEED_COLUMN_SUBSTRINGS = frozenset(
    {
        "wind_speed",
        "ef_",
    }
)


def is_grade_adjusted_pace_metric(metric_key: str, column: Optional[str] = None) -> bool:
    if column in GRADE_ADJUSTED_SPEED_COLUMNS:
        return True
    return metric_key in GRADE_ADJUSTED_PACE_METRIC_KEYS


def is_running_speed_metric(metric_key: str, column: Optional[str] = None) -> bool:
    if is_grade_adjusted_pace_metric(metric_key, column):
        return False
    if any(part in metric_key for part in EXCLUDED_SPEED_COLUMN_SUBSTRINGS):
        return False
    if metric_key.startswith("running.speed_"):
        return True
    if column in SPEED_MPS_COLUMN_NAMES:
        return True
    if metric_key.endswith("_speed_mps") or metric_key.endswith(".average_speed"):
        return True
    return False


def is_pace_metric(metric_key: str, column: Optional[str] = None) -> bool:
    if is_grade_adjusted_pace_metric(metric_key, column):
        return True
    if column in PACE_SEC_COLUMN_NAMES:
        return True
    if metric_key == "activity.grade_adjusted_pace_sec_per_km":
        return True
    if metric_key.endswith("pace_sec_per_km") or metric_key == "weather.adjusted_pace":
        return True
    if metric_key.endswith(".avg_pace") or metric_key.endswith(".best_pace"):
        return True
    return False


def is_internal_speed_metric(metric_key: str, column: Optional[str] = None) -> bool:
    return column in INTERNAL_SPEED_COLUMN_NAMES or "raw_lactate_threshold_speed" in metric_key


def is_derived_speed_metric(metric_key: str) -> bool:
    return metric_key == "running.critical_speed" or metric_key.startswith("running.speed_")


def apply_pace_user_display_to_point(
    point: Dict[str, Any],
    pace_sec_per_km: Optional[float],
) -> Dict[str, Any]:
    """Bruk M:SS/km som brukerrettet value; behold numerisk pace_sec_per_km."""
    pace_payload = build_pace_payload(pace_sec_per_km)
    point["pace_sec_per_km"] = pace_payload["value_pace_sec_per_km"]
    point["pace_display"] = pace_payload["pace_display"]
    point["value"] = pace_payload["pace_display"]
    point["speed_kmh"] = pace_payload["speed_kmh"]
    point["display_unit"] = PACE_DISPLAY_UNIT
    return point


def enrich_dict_pace_fields(
    payload: Dict[str, Any],
    *,
    sec_key: str = "pace_sec_per_km",
    display_key: str = "pace_display",
    user_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Legg til M:SS/km display-felt ved siden av numerisk pace_sec_per_km."""
    pace_sec = payload.get(sec_key)
    if pace_sec is None:
        return payload
    display = pace_sec_to_display(pace_sec)
    payload[display_key] = display
    if user_key:
        payload[user_key] = display
    return payload


def mcp_display_unit(metric_key: str, column: Optional[str] = None) -> Optional[str]:
    if is_internal_speed_metric(metric_key, column):
        return "internal"
    if is_grade_adjusted_pace_metric(metric_key, column):
        return PACE_DISPLAY_UNIT
    if is_pace_metric(metric_key, column):
        return PACE_DISPLAY_UNIT
    if is_running_speed_metric(metric_key, column) or is_derived_speed_metric(metric_key):
        return "km/h"
    return None


def infer_metric_unit_for_column(column_name: str) -> Optional[str]:
    name = column_name.lower()
    if name in GRADE_ADJUSTED_SPEED_COLUMNS:
        return PACE_DISPLAY_UNIT
    if name in INTERNAL_SPEED_COLUMN_NAMES:
        return "internal"
    if name in PACE_SEC_COLUMN_NAMES or "pace" in name:
        return PACE_DISPLAY_UNIT
    if name in SPEED_MPS_COLUMN_NAMES or (
        "speed" in name and not any(ex in name for ex in EXCLUDED_SPEED_COLUMN_SUBSTRINGS)
    ):
        return "km/h"
    return None


def _summary_row_totals(row: Any) -> tuple[Optional[float], Optional[float]]:
    distance = getattr(row, "total_distance", None)
    duration = getattr(row, "total_duration", None)
    if distance is None or duration is None:
        return None, None
    return float(distance), float(duration)


def enrich_stored_metric_point(
    metric_key: str,
    point: Dict[str, Any],
    row: Any,
    definition: Dict[str, Any],
) -> Dict[str, Any]:
    """Berik et lagret metrikkpunkt med km/t, pace og konsistenssjekker."""
    column = definition.get("column")
    raw_value = point.get("value")

    if definition.get("derived") in {"activity_pace", "grade_adjusted_pace"}:
        enriched = apply_pace_user_display_to_point(point, raw_value)
        if definition.get("derived") == "grade_adjusted_pace" and isinstance(row, object):
            speed_mps = getattr(row, "avg_grade_adjusted_speed", None)
            if speed_mps is not None:
                enriched["speed_mps_internal"] = round(float(speed_mps), 4)
                enriched["speed_kmh"] = mps_to_kmh(float(speed_mps))
            enriched["source"] = "garmin_avgGradeAdjustedSpeed"
            enriched["note"] = (
                "Grade-adjusted pace fra Garmin (avgGradeAdjustedSpeed); "
                "lagret internt som m/s i avg_grade_adjusted_speed."
            )
        return enriched

    if is_grade_adjusted_pace_metric(metric_key, column):
        speed_mps = float(raw_value) if raw_value is not None else None
        pace_sec = mps_to_pace_sec_per_km(speed_mps)
        apply_pace_user_display_to_point(point, pace_sec)
        if speed_mps is not None:
            point["speed_mps_internal"] = round(speed_mps, 4)
            point["speed_kmh"] = mps_to_kmh(speed_mps)
        point["source"] = "garmin_avgGradeAdjustedSpeed"
        point["note"] = (
            "Grade-adjusted pace fra Garmin (avgGradeAdjustedSpeed); "
            "lagret internt som m/s i avg_grade_adjusted_speed."
        )
        return point

    if is_internal_speed_metric(metric_key, column):
        normalized = normalize_lactate_threshold_raw_speed(raw_value)
        normalized_mps = None
        if hasattr(row, "lactate_threshold_speed") and row.lactate_threshold_speed:
            normalized_mps = float(row.lactate_threshold_speed)
        elif normalized is not None:
            normalized_mps = normalized
        point["display_unit"] = "internal"
        point["unit"] = "internal"
        point["raw_garmin_encoding"] = raw_value
        if normalized_mps is not None:
            point.update(build_speed_pace_payload(normalized_mps))
            point["normalized_speed_mps"] = round(normalized_mps, 4)
            point["validation"] = validate_lactate_threshold_speed(normalized_mps)
        else:
            point["validation"] = {"valid": False, "suspicious": True, "reason": "cannot_normalize_raw_value"}
        return point

    if is_pace_metric(metric_key, column):
        apply_pace_user_display_to_point(point, raw_value)
        if column == "avg_pace" or metric_key.endswith(".avg_pace"):
            distance, duration = _summary_row_totals(row)
            if distance and duration and raw_value is not None:
                avg_speed = getattr(row, "avg_speed", None)
                point["consistency"] = check_speed_pace_consistency(
                    avg_speed_mps=avg_speed,
                    avg_pace_sec_per_km=raw_value,
                    total_distance_m=distance,
                    total_duration_s=duration,
                )
        return point

    if is_running_speed_metric(metric_key, column):
        speed_mps = float(raw_value) if raw_value is not None else None
        speed_payload = build_speed_pace_payload(speed_mps)
        point["value"] = speed_payload["speed_kmh"]
        point["pace_sec_per_km"] = speed_payload["pace_sec_per_km"]
        point["pace_display"] = speed_payload["pace_display"]
        point["speed_kmh"] = speed_payload["speed_kmh"]
        point["display_unit"] = "km/h"

        if column == "lactate_threshold_speed" and isinstance(row, LactateThresholdHistory):
            point["validation"] = validate_lactate_threshold_speed(speed_mps)
            if row.raw_lactate_threshold_speed is not None:
                point["raw_garmin_encoding"] = row.raw_lactate_threshold_speed

        if column in {"avg_speed", "best_speed"} or metric_key.endswith(".avg_speed"):
            distance, duration = _summary_row_totals(row)
            avg_pace = getattr(row, "avg_pace", None)
            moving_duration = getattr(row, "moving_duration_s", None)
            elapsed_duration = getattr(row, "elapsed_duration_s", None)
            if distance and duration:
                point["speed_basis"] = {
                    "distance_m": distance,
                    "duration_s": duration,
                    "note": "avg_speed and avg_pace derived from total_distance / total_duration",
                }
                if moving_duration or elapsed_duration:
                    point["speed_basis"]["moving_duration_s"] = moving_duration
                    point["speed_basis"]["elapsed_duration_s"] = elapsed_duration
                point["consistency"] = check_speed_pace_consistency(
                    avg_speed_mps=speed_mps,
                    avg_pace_sec_per_km=avg_pace,
                    total_distance_m=distance,
                    total_duration_s=duration,
                )
                expected_speed, expected_pace = aggregate_speed_pace_from_totals(distance, duration)
                if expected_speed is not None:
                    point["expected_speed_kmh"] = mps_to_kmh(expected_speed)
                    point["expected_pace_sec_per_km"] = mps_to_pace_sec_per_km(expected_speed)
                    point["expected_pace_display"] = pace_sec_to_display(expected_pace)

        return point

    return point


def _export_definition_for_key(
    metric_key: str,
    definition: Dict[str, Any],
) -> Dict[str, Any]:
    """Tilpass catalog-definisjon for skalar eksport (alias vs. kanonisk grade-adjusted)."""
    column = definition.get("column")
    if (
        is_grade_adjusted_pace_metric(metric_key, column)
        and definition.get("derived") == "grade_adjusted_pace"
        and metric_key != "activity.grade_adjusted_pace_sec_per_km"
    ):
        return {key: value for key, value in definition.items() if key != "derived"}
    return definition


def _prepare_export_stored_scalar(
    metric_key: str,
    raw_value: Any,
    definition: Dict[str, Any],
) -> Any:
    """Speil _metric_point-verdiuttrekk når eksport kun har siste lagrede skalar."""
    if raw_value is None:
        return None
    if definition.get("derived") == "grade_adjusted_pace":
        return mps_to_pace_sec_per_km(float(raw_value))
    return raw_value


def mcp_export_display_value(
    metric_key: str,
    raw_value: Any,
    *,
    source: str,
    definition: Optional[Dict[str, Any]] = None,
) -> tuple[Any, Optional[str]]:
    """Formatér skalar verdi/enhet for MCP fresh export (samme semantikk som timeseries)."""
    definition = definition or {}
    export_definition = _export_definition_for_key(metric_key, definition)
    column = export_definition.get("column")
    fallback_unit = mcp_display_unit(metric_key, column) or export_definition.get("unit")

    if raw_value is None:
        return None, fallback_unit

    prepared = raw_value
    if source == "stored":
        prepared = _prepare_export_stored_scalar(metric_key, raw_value, export_definition)

    point: Dict[str, Any] = {"value": prepared}
    if isinstance(prepared, (int, float)):
        point["value"] = round(float(prepared), 3)

    if source == "derived":
        enriched = enrich_derived_metric_point(metric_key, point)
    else:
        enriched = enrich_stored_metric_point(metric_key, point, None, export_definition)

    display_value = enriched.get("value")
    display_unit = enriched.get("display_unit") or enriched.get("unit") or fallback_unit
    return display_value, display_unit


def enrich_derived_metric_point(metric_key: str, point: Dict[str, Any]) -> Dict[str, Any]:
    """Berik derived fart- og pace-metrikker."""
    if is_pace_metric(metric_key):
        raw_pace = point.get("value")
        if raw_pace is None or not isinstance(raw_pace, (int, float)):
            return point
        return apply_pace_user_display_to_point(point, float(raw_pace))

    if not is_derived_speed_metric(metric_key):
        return point

    raw_mps = point.get("value")
    if raw_mps is None:
        return point

    speed_mps = float(raw_mps)
    speed_payload = build_speed_pace_payload(speed_mps)
    point["value"] = speed_payload["speed_kmh"]
    point["pace_sec_per_km"] = speed_payload["pace_sec_per_km"]
    point["pace_display"] = speed_payload["pace_display"]
    point["speed_kmh"] = speed_payload["speed_kmh"]
    point["display_unit"] = "km/h"
    point["speed_mps_internal"] = round(speed_mps, 4)
    point["validation"] = validate_running_speed_window(metric_key, speed_mps)
    return point


def enrich_activity_summary_speed_fields(summary: Dict[str, Any]) -> Dict[str, Any]:
    """Konverter activity summary fra m/s til km/t + pace."""
    speed_mps = summary.pop("average_speed_mps", None)
    if speed_mps is None:
        speed_mps = summary.get("average_speed")
    if speed_mps is not None:
        payload = build_speed_pace_payload(speed_mps)
        summary["average_speed_kmh"] = payload["speed_kmh"]
        summary["average_pace_sec_per_km"] = payload["pace_sec_per_km"]
        summary["average_pace_display"] = payload["pace_display"]
        summary["average_speed_mps_internal"] = round(float(speed_mps), 4)

    pace = summary.get("pace_sec_per_km")
    if pace is not None and "average_pace_display" not in summary:
        enrich_dict_pace_fields(
            summary,
            user_key="average_pace",
        )
    elif summary.get("average_pace_display"):
        summary["average_pace"] = summary["average_pace_display"]
    return summary


def enrich_athlete_threshold_payload(threshold_row: Optional[LactateThresholdHistory]) -> Dict[str, Any]:
    if threshold_row is None:
        return {
            "observed_at": None,
            "lt2_heart_rate_bpm": None,
            "lt2_speed_kmh": None,
            "lt2_pace_sec_per_km": None,
            "lt2_pace_display": None,
            "source": None,
            "validation": None,
        }

    speed_mps = threshold_row.lactate_threshold_speed
    payload = build_speed_pace_payload(speed_mps)
    result = {
        "observed_at": threshold_row.observed_at.isoformat() if threshold_row.observed_at else None,
        "lt2_heart_rate_bpm": threshold_row.lactate_threshold_heart_rate,
        "lt2_speed_kmh": payload["speed_kmh"],
        "lt2_pace_sec_per_km": payload["pace_sec_per_km"],
        "lt2_pace_display": payload["pace_display"],
        "source": threshold_row.source,
        "validation": validate_lactate_threshold_speed(speed_mps),
    }
    if threshold_row.raw_lactate_threshold_speed is not None:
        result["raw_garmin_encoding"] = threshold_row.raw_lactate_threshold_speed
        result["raw_normalized_speed_kmh"] = mps_to_kmh(
            normalize_lactate_threshold_raw_speed(threshold_row.raw_lactate_threshold_speed)
        )
    return result


def audit_user_facing_speed_units(catalog_metrics: list[Dict[str, Any]]) -> list[str]:
    """Returner metrikker som fortsatt eksponerer m/s som brukerrettet enhet."""
    issues = []
    for metric in catalog_metrics:
        key = metric.get("key", "")
        unit = metric.get("unit")
        column = None
        if "." in key:
            column = key.split(".", 1)[1]
        if unit == "m/s" and not is_internal_speed_metric(key, column):
            if is_running_speed_metric(key, column) or is_derived_speed_metric(key):
                issues.append(key)
    return issues
