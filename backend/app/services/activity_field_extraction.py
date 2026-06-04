from __future__ import annotations

from typing import Any, Dict, Optional


def _coerce_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _coerce_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_garmin_elapsed_duration(
    raw: Any,
    timer_duration: Optional[float] = None,
) -> Optional[float]:
    """
    Garmin activitylist returnerer elapsedDuration i millisekunder.
    Lagres som sekunder i activities.elapsed_duration.
    """
    value = _coerce_float(raw)
    if value is None:
        return None

    if timer_duration is not None and timer_duration > 0:
        if abs(value - timer_duration) / timer_duration <= 0.05:
            return value
        seconds = value / 1000.0
        if abs(seconds - timer_duration) / timer_duration <= 0.05:
            return seconds

    if value >= 1000:
        return value / 1000.0
    return value


def normalize_garmin_moving_duration(
    raw: Any,
    timer_duration: Optional[float] = None,
) -> Optional[float]:
    """
    movingDuration kommer som sekunder fra Garmin list/summary payloads.
    """
    value = _coerce_float(raw)
    if value is None:
        return None

    if timer_duration is not None and timer_duration > 0:
        if abs(value - timer_duration) / timer_duration <= 0.05:
            return value
        seconds = value / 1000.0
        if abs(seconds - timer_duration) / timer_duration <= 0.05:
            return seconds

    return value


def extract_garmin_weather_fields(act_data: Dict[str, Any]) -> Dict[str, Optional[float | str]]:
    """
    Temperatur fra Garmin activitylist (min/max under økta).
    Vind hentes normalt ikke her — bruk MET/Frost i sync_service når konfigurert.
    """
    min_t = _coerce_float(act_data.get("minTemperature"))
    max_t = _coerce_float(act_data.get("maxTemperature"))
    temperature = None
    if min_t is not None and max_t is not None:
        temperature = (min_t + max_t) / 2.0
    elif min_t is not None:
        temperature = min_t
    elif max_t is not None:
        temperature = max_t

    weather_condition = "garmin_list" if temperature is not None else None
    return {
        "temperature": temperature,
        "weather_condition": weather_condition,
    }


def extract_activity_list_fields(act_data: Dict[str, Any]) -> Dict[str, Optional[float | int]]:
    """Henter felter som allerede finnes i Garmin activitylist JSON."""
    duration = _coerce_float(act_data.get("duration"))

    return {
        "moving_duration": normalize_garmin_moving_duration(
            act_data.get("movingDuration"),
            duration,
        ),
        "elapsed_duration": normalize_garmin_elapsed_duration(
            act_data.get("elapsedDuration"),
            duration,
        ),
        "total_steps": _coerce_int(act_data.get("steps")),
        "min_elevation": _coerce_float(act_data.get("minElevation")),
        "max_elevation": _coerce_float(act_data.get("maxElevation")),
    }


def extract_activity_summary_fields(summary: Dict[str, Any]) -> Dict[str, Optional[float | int]]:
    """Henter tilsvarende felter fra activity-service summaryDTO."""
    duration = _coerce_float(summary.get("duration"))

    return {
        "moving_duration": normalize_garmin_moving_duration(
            summary.get("movingDuration"),
            duration,
        ),
        "elapsed_duration": normalize_garmin_elapsed_duration(
            summary.get("elapsedDuration"),
            duration,
        ),
        "min_elevation": _coerce_float(summary.get("minElevation")),
        "max_elevation": _coerce_float(summary.get("maxElevation")),
    }
