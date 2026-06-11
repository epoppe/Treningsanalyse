"""Hjelpere for Body Battery fra Garmin wellness-tidsserie (body_battery_values_array)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple


def _to_utc_ms(value: datetime) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp() * 1000)


def _entry_timestamp_ms(entry: Sequence[Any]) -> Optional[int]:
    if not entry:
        return None
    ts = entry[0]
    return int(ts) if isinstance(ts, (int, float)) else None


def _entry_value(entry: Sequence[Any]) -> Optional[float]:
    if len(entry) < 3:
        return None
    value = entry[2]
    if isinstance(value, (int, float)):
        return float(value)
    return None


def body_battery_value_at(
    values_array: Sequence[Sequence[Any]],
    target: datetime,
) -> Optional[float]:
    """Returnerer siste målte Body Battery ved eller før target."""
    if not values_array:
        return None
    target_ms = _to_utc_ms(target)
    best_value: Optional[float] = None
    for entry in values_array:
        ts = _entry_timestamp_ms(entry)
        if ts is None or ts > target_ms:
            break
        value = _entry_value(entry)
        if value is not None:
            best_value = value
    return best_value


def derive_activity_body_battery_from_timeseries(
    start_time: datetime,
    duration_s: Optional[float],
    values_array: Sequence[Sequence[Any]],
) -> Dict[str, Optional[float]]:
    """
    Utled start og delta for en aktivitet fra daglig Body Battery-tidsserie.

    Returnerer tomme felt når tidsserien ikke dekker aktivitetsvinduet.
    """
    if not values_array or start_time is None:
        return {"body_battery_start": None, "activity_body_battery_delta": None}

    start_value = body_battery_value_at(values_array, start_time)
    if start_value is None:
        return {"body_battery_start": None, "activity_body_battery_delta": None}

    if duration_s is None or duration_s <= 0:
        return {"body_battery_start": round(start_value, 1), "activity_body_battery_delta": None}

    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    end_time = start_time.timestamp() + float(duration_s)
    end_dt = datetime.fromtimestamp(end_time, tz=timezone.utc)
    end_value = body_battery_value_at(values_array, end_dt)
    if end_value is None:
        return {"body_battery_start": round(start_value, 1), "activity_body_battery_delta": None}

    return {
        "body_battery_start": round(start_value, 1),
        "activity_body_battery_delta": round(end_value - start_value, 1),
    }


def derive_daily_body_battery_from_timeseries(
    values_array: Sequence[Sequence[Any]],
) -> Dict[str, Optional[float]]:
    """
    Utled daglige Body Battery-felter fra wellness-tidsserie.

    Returnerer charged/drained/net/start/end/max/min når tidsserien har minst to punkter.
    """
    if not values_array or len(values_array) < 2:
        return {
            "body_battery_charged_start": None,
            "body_battery_drained_start": None,
            "body_battery_charged": None,
            "body_battery_drained": None,
            "net_charge": None,
            "max_body_battery": None,
            "min_body_battery": None,
        }

    values: List[float] = []
    for entry in values_array:
        value = _entry_value(entry)
        if value is not None:
            values.append(value)

    if len(values) < 2:
        return {
            "body_battery_charged_start": None,
            "body_battery_drained_start": None,
            "body_battery_charged": None,
            "body_battery_drained": None,
            "net_charge": None,
            "max_body_battery": max(values) if values else None,
            "min_body_battery": min(values) if values else None,
        }

    start_value = values[0]
    end_value = values[-1]
    charged = 0.0
    drained = 0.0
    for prev, current in zip(values, values[1:]):
        delta = current - prev
        if delta > 0:
            charged += delta
        elif delta < 0:
            drained += abs(delta)

    net_charge = end_value - start_value
    return {
        "body_battery_charged_start": round(start_value, 1),
        "body_battery_drained_start": round(start_value, 1),
        "body_battery_charged": round(charged, 1),
        "body_battery_drained": round(drained, 1),
        "net_charge": round(net_charge, 1),
        "max_body_battery": round(max(values), 1),
        "min_body_battery": round(min(values), 1),
    }


def enrich_body_battery_day_data(day_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fyll manglende charged/drained/start/net fra wellness-tidsserie når API kun ga max/min.

    Tidsserien persisteres ikke i DB; utledning skjer ved sync/backfill fra rå payload.
    """
    if not isinstance(day_data, dict):
        return day_data

    values_array = day_data.get("body_battery_values_array") or day_data.get("values")
    if not values_array:
        if (
            day_data.get("body_battery_charged") is not None
            and day_data.get("body_battery_drained") is not None
            and day_data.get("net_charge") is None
        ):
            day_data["net_charge"] = round(
                float(day_data["body_battery_charged"]) - float(day_data["body_battery_drained"]),
                1,
            )
        return day_data

    derived = derive_daily_body_battery_from_timeseries(values_array)
    for field in (
        "body_battery_charged_start",
        "body_battery_drained_start",
        "body_battery_charged",
        "body_battery_drained",
        "net_charge",
        "max_body_battery",
        "min_body_battery",
    ):
        if day_data.get(field) is None and derived.get(field) is not None:
            day_data[field] = derived[field]
    return day_data
