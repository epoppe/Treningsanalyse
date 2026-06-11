"""Konvertering og validering av hastighet (m/s) og pace (s/km) for MCP og API."""

from __future__ import annotations

import math
import re
from typing import Any, Dict, Optional

# Løping: typisk terskel ca. 2.5–6 m/s; utenfor dette er verdien mistenkelig.
LT_SPEED_MIN_MPS = 1.5
LT_SPEED_MAX_MPS = 7.0

# Toleranse for automatiske konsistenssjekker.
PACE_CONSISTENCY_TOLERANCE_SEC = 2.0
SPEED_CONSISTENCY_TOLERANCE_PCT = 0.01
PACE_DISPLAY_UNIT = "M:SS/km"
PACE_DISPLAY_PATTERN = re.compile(r"^\d+:\d{2}/km$")


def _is_finite_number(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return False
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(numeric)


def mps_to_kmh(mps: Optional[float]) -> Optional[float]:
    """Konverter m/s til km/t."""
    if not _is_finite_number(mps) or float(mps) <= 0:
        return None
    return round(float(mps) * 3.6, 3)


def mps_to_pace_sec_per_km(mps: Optional[float]) -> Optional[float]:
    """Konverter m/s til pace i sekunder per km."""
    if not _is_finite_number(mps) or float(mps) <= 0:
        return None
    return round(1000.0 / float(mps), 1)


def pace_sec_to_mmss(seconds: Optional[float]) -> Optional[str]:
    """Formater pace-sekunder som M:SS (f.eks. 382.1 -> '6:22')."""
    if not _is_finite_number(seconds) or float(seconds) <= 0:
        return None
    total = int(round(float(seconds)))
    minutes = total // 60
    secs = total % 60
    return f"{minutes}:{secs:02d}"


def pace_sec_to_display(seconds: Optional[float]) -> Optional[str]:
    """Formater pace som M:SS/km."""
    formatted = pace_sec_to_mmss(seconds)
    return f"{formatted}/km" if formatted else None


def kmh_to_mps(kmh: Optional[float]) -> Optional[float]:
    if not _is_finite_number(kmh) or float(kmh) <= 0:
        return None
    return float(kmh) / 3.6


def pace_sec_per_km_to_mps(pace_sec: Optional[float]) -> Optional[float]:
    if not _is_finite_number(pace_sec) or float(pace_sec) <= 0:
        return None
    return 1000.0 / float(pace_sec)


def build_speed_pace_payload(
    speed_mps: Optional[float],
    *,
    include_internal_mps: bool = False,
) -> Dict[str, Any]:
    """Bygg standard MCP-felt for en hastighet lagret internt som m/s."""
    pace_sec = mps_to_pace_sec_per_km(speed_mps)
    payload: Dict[str, Any] = {
        "speed_kmh": mps_to_kmh(speed_mps),
        "pace_sec_per_km": pace_sec,
        "pace_display": pace_sec_to_display(pace_sec),
    }
    if include_internal_mps and _is_finite_number(speed_mps):
        payload["speed_mps_internal"] = round(float(speed_mps), 4)
        payload["unit_internal"] = "m/s"
    return payload


def build_pace_payload(pace_sec_per_km: Optional[float]) -> Dict[str, Any]:
    """Bygg MCP-felt for pace lagret som s/km."""
    speed_mps = pace_sec_per_km_to_mps(pace_sec_per_km)
    return {
        "value_pace_sec_per_km": round(float(pace_sec_per_km), 1) if _is_finite_number(pace_sec_per_km) else None,
        "pace_display": pace_sec_to_display(pace_sec_per_km),
        "speed_kmh": mps_to_kmh(speed_mps),
    }


def normalize_lactate_threshold_raw_speed(raw_speed: Optional[float]) -> Optional[float]:
    """Skaler Garmin raw terskelfart (0.2–0.7) til m/s når nødvendig."""
    if not _is_finite_number(raw_speed) or float(raw_speed) <= 0:
        return None
    speed = float(raw_speed)
    if 2.0 <= speed <= 6.0:
        return speed
    if 0.2 <= speed <= 0.7:
        scaled = speed * 10.0
        if 2.0 <= scaled <= 6.0:
            return scaled
    return None


def validate_lactate_threshold_speed(speed_mps: Optional[float]) -> Dict[str, Any]:
    """Flagg terskelfart utenfor plausibelt løpeområde."""
    if not _is_finite_number(speed_mps):
        return {"valid": False, "suspicious": True, "reason": "missing_or_invalid"}
    speed = float(speed_mps)
    if speed < LT_SPEED_MIN_MPS:
        return {
            "valid": False,
            "suspicious": True,
            "reason": f"below_plausible_running_threshold ({speed:.3f} m/s < {LT_SPEED_MIN_MPS} m/s)",
        }
    if speed > LT_SPEED_MAX_MPS:
        return {
            "valid": False,
            "suspicious": True,
            "reason": f"above_plausible_running_threshold ({speed:.3f} m/s > {LT_SPEED_MAX_MPS} m/s)",
        }
    return {"valid": True, "suspicious": False, "reason": None}


def aggregate_speed_pace_from_totals(
    total_distance_m: Optional[float],
    total_duration_s: Optional[float],
) -> tuple[Optional[float], Optional[float]]:
    """
    Beregn vektet avg_speed og matchende avg_pace fra total distanse/varighet.
    """
    if not _is_finite_number(total_distance_m) or not _is_finite_number(total_duration_s):
        return None, None
    distance = float(total_distance_m)
    duration = float(total_duration_s)
    if distance <= 0 or duration <= 0:
        return None, None
    avg_speed = distance / duration
    avg_pace = 1000.0 / avg_speed
    return avg_speed, avg_pace


def check_speed_pace_consistency(
    *,
    avg_speed_mps: Optional[float],
    avg_pace_sec_per_km: Optional[float],
    total_distance_m: Optional[float] = None,
    total_duration_s: Optional[float] = None,
) -> Dict[str, Any]:
    """Automatisk konsistenssjekk for aggregeringer."""
    issues = []

    if total_distance_m is not None and total_duration_s is not None:
        expected_speed, expected_pace = aggregate_speed_pace_from_totals(
            total_distance_m,
            total_duration_s,
        )
        if expected_speed is not None and _is_finite_number(avg_speed_mps):
            rel_err = abs(float(avg_speed_mps) - expected_speed) / expected_speed
            if rel_err > SPEED_CONSISTENCY_TOLERANCE_PCT:
                issues.append(
                    f"avg_speed {float(avg_speed_mps):.4f} m/s avviker "
                    f"{rel_err * 100:.2f}% fra distance/duration ({expected_speed:.4f} m/s)"
                )

    if _is_finite_number(avg_speed_mps) and float(avg_speed_mps) > 0:
        expected_pace = mps_to_pace_sec_per_km(avg_speed_mps)
        if _is_finite_number(avg_pace_sec_per_km) and expected_pace is not None:
            pace_delta = abs(float(avg_pace_sec_per_km) - expected_pace)
            if pace_delta > PACE_CONSISTENCY_TOLERANCE_SEC:
                issues.append(
                    f"avg_pace {float(avg_pace_sec_per_km):.1f} s/km avviker "
                    f"{pace_delta:.1f} s/km fra 1000/avg_speed ({expected_pace:.1f} s/km)"
                )

        kmh_from_mps = mps_to_kmh(avg_speed_mps)
        if kmh_from_mps is not None:
            back_mps = kmh_to_mps(kmh_from_mps)
            if back_mps is not None and abs(back_mps - float(avg_speed_mps)) / float(avg_speed_mps) > 0.001:
                issues.append("kmh/mps round-trip mismatch")

    return {
        "consistent": len(issues) == 0,
        "issues": issues,
    }


_RUNNING_SPEED_WINDOW_KMH_FLAG: Dict[str, float] = {
    "30s": 30.0,
    "1m": 28.0,
    "3m": 26.0,
    "5m": 24.0,
    "10m": 22.0,
    "20m": 20.0,
    "40m": 19.0,
    "60m": 18.0,
}


def running_speed_window_key(metric_key: str) -> Optional[str]:
    match = re.search(r"running\.speed_(\d+[smh]+)", metric_key)
    if not match:
        return None
    return match.group(1)


def validate_running_speed_window(metric_key: str, speed_mps: Optional[float]) -> Dict[str, Any]:
    """Flagg ekstreme best-effort fart-vinduer."""
    window = running_speed_window_key(metric_key)
    if window is None or not _is_finite_number(speed_mps):
        return {"suspicious": False, "reason": None}
    kmh = mps_to_kmh(speed_mps)
    if kmh is None:
        return {"suspicious": False, "reason": None}
    threshold = _RUNNING_SPEED_WINDOW_KMH_FLAG.get(window)
    if threshold is None:
        return {"suspicious": False, "reason": None}
    if kmh > threshold:
        return {
            "suspicious": True,
            "reason": (
                f"speed {kmh:.1f} km/h exceeds plausible {window} window threshold "
                f"({threshold:.0f} km/h) — possible GPS spike"
            ),
        }
    return {"suspicious": False, "reason": None}
