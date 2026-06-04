from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Mapping, Optional

from ..database.models.sleep import Sleep


def sleep_minutes_to_seconds(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value) * 60.0
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        numeric = float(value)
        if numeric > 1_000_000_000_000:
            numeric /= 1000.0
        try:
            return datetime.fromtimestamp(numeric, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _coerce_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _derive_sleep_quality(score: Optional[float]) -> Optional[str]:
    if score is None:
        return None
    if score >= 85:
        return "excellent"
    if score >= 70:
        return "good"
    if score >= 55:
        return "fair"
    return "poor"


def apply_sleep_data_to_row(row: Sleep, data: Mapping[str, Any]) -> None:
    total_sleep_time = sleep_minutes_to_seconds(data.get("sleep_time"))
    if total_sleep_time is None:
        total_sleep_time = sleep_minutes_to_seconds(data.get("total_sleep"))
    if total_sleep_time is not None:
        row.total_sleep_time = total_sleep_time

    duration_fields = {
        "deep_sleep": "deep_sleep_time",
        "light_sleep": "light_sleep_time",
        "rem_sleep": "rem_sleep_time",
        "awake_time": "awake_time",
    }
    for key, attr in duration_fields.items():
        seconds = sleep_minutes_to_seconds(data.get(key))
        if seconds is not None:
            setattr(row, attr, seconds)

    direct_float_fields = {
        "sleep_score": "sleep_score",
        "overall_score": "overall_score",
        "deep_sleep_percent": "deep_sleep_percent",
        "light_sleep_percent": "light_sleep_percent",
        "rem_sleep_percent": "rem_sleep_percent",
        "awake_percent": "awake_percent",
        "sleep_efficiency": "sleep_efficiency",
        "average_heart_rate": "average_heart_rate",
        "lowest_heart_rate": "lowest_heart_rate",
        "highest_heart_rate": "highest_heart_rate",
        "heart_rate_variability": "heart_rate_variability",
        "average_spo2": "average_spo2",
        "lowest_spo2": "lowest_spo2",
        "average_respiration_rate": "average_respiration_rate",
        "stress_score": "stress_score",
        "recovery_score": "recovery_score",
        "movement_score": "movement_score",
    }
    for key, attr in direct_float_fields.items():
        value = _coerce_float(data.get(key))
        if value is not None:
            setattr(row, attr, value)

    sleep_latency = data.get("sleep_latency")
    if sleep_latency is not None:
        latency = _coerce_float(sleep_latency)
        if latency is not None:
            row.sleep_latency = latency

    direct_int_fields = {
        "wake_episodes": "wake_episodes",
        "restless_moments": "restless_moments",
    }
    for key, attr in direct_int_fields.items():
        value = _coerce_int(data.get(key))
        if value is not None:
            setattr(row, attr, value)

    bedtime = _parse_datetime(data.get("bedtime"))
    if bedtime is not None:
        row.bedtime = bedtime

    wake_time = _parse_datetime(data.get("wake_time"))
    if wake_time is not None:
        row.wake_time = wake_time

    sleep_quality = data.get("sleep_quality")
    if isinstance(sleep_quality, str) and sleep_quality.strip():
        row.sleep_quality = sleep_quality.strip().lower()
    else:
        derived = _derive_sleep_quality(
            _coerce_float(data.get("overall_score")) or _coerce_float(data.get("sleep_score"))
        )
        if derived is not None:
            row.sleep_quality = derived

    device_name = data.get("device_name")
    if isinstance(device_name, str) and device_name.strip():
        row.device_name = device_name.strip()

    detailed = data.get("detailed_sleep_data")
    if detailed is not None:
        row.detailed_sleep_data = detailed
