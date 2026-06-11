"""Utledning av søvnfelter fra eksisterende lagrede Sleep-rader (uten API-kall)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional


def _coerce_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sleep_quality_from_score(score: Optional[float]) -> Optional[str]:
    if score is None:
        return None
    if score >= 85:
        return "excellent"
    if score >= 70:
        return "good"
    if score >= 55:
        return "fair"
    return "poor"


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        numeric = float(value)
        if numeric > 1_000_000_000_000:
            numeric /= 1000.0
        try:
            return datetime.fromtimestamp(numeric, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    return None


def _score_block_value(block: Any) -> Optional[float]:
    if not isinstance(block, dict):
        return None
    return _coerce_float(block.get("value"))


def extract_sleep_fields_from_detailed_data(data: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Trekker ut sidefelter fra lagret detailed_sleep_data (garth DailySleepDTO, ofte snake_case).
    """
    if not data:
        return {}

    result: Dict[str, Any] = {}

    scores = data.get("sleep_scores")
    if isinstance(scores, dict):
        overall = _score_block_value(scores.get("overall"))
        if overall is not None:
            result["overall_score"] = overall
            result.setdefault("sleep_score", overall)
        for score_key, attr in (
            ("deep_percentage", "deep_sleep_percent"),
            ("light_percentage", "light_sleep_percent"),
            ("rem_percentage", "rem_sleep_percent"),
        ):
            value = _score_block_value(scores.get(score_key))
            if value is not None:
                result[attr] = value

    bedtime = _parse_timestamp(
        data.get("sleep_start_timestamp_gmt")
        or data.get("sleepStartTimestampGMT")
        or data.get("sleep_start_timestamp_local")
        or data.get("sleepStartTimestampLocal")
    )
    if bedtime is not None:
        result["bedtime"] = bedtime

    wake_time = _parse_timestamp(
        data.get("sleep_end_timestamp_gmt")
        or data.get("sleepEndTimestampGMT")
        or data.get("sleep_end_timestamp_local")
        or data.get("sleepEndTimestampLocal")
    )
    if wake_time is not None:
        result["wake_time"] = wake_time

    wake_episodes = _coerce_int(data.get("awake_count") or data.get("awakeCount"))
    if wake_episodes is not None:
        result["wake_episodes"] = wake_episodes

    stress = _coerce_float(data.get("avg_sleep_stress") or data.get("avgSleepStress"))
    if stress is not None:
        result["stress_score"] = stress

    respiration = _coerce_float(
        data.get("average_respiration_value")
        or data.get("averageRespirationValue")
        or data.get("average_respiration_rate")
    )
    if respiration is not None:
        result["average_respiration_rate"] = respiration

    for target, keys in (
        ("average_spo2", ("average_sp_o2_value", "averageSpo2Value", "average_spo2", "averageSpo2", "avgSpo2")),
        ("lowest_spo2", ("lowest_sp_o2_value", "lowestSpo2Value", "lowest_spo2", "lowestSpo2", "minSpo2")),
        (
            "average_heart_rate",
            ("average_sp_o2_hr_sleep", "averageSpO2HrSleep", "average_heart_rate", "averageHeartRate", "avgHeartRate"),
        ),
        ("lowest_heart_rate", ("lowest_heart_rate", "lowestHeartRate", "minHeartRate")),
        ("highest_heart_rate", ("highest_heart_rate", "highestHeartRate", "maxHeartRate")),
        (
            "heart_rate_variability",
            ("heart_rate_variability", "heartRateVariability", "averageHrv", "average_hrv"),
        ),
        ("recovery_score", ("recovery_score", "recoveryScore")),
        ("movement_score", ("movement_score", "movementScore")),
    ):
        for key in keys:
            value = _coerce_float(data.get(key))
            if value is not None:
                result[target] = value
                break

    restless = _coerce_int(
        data.get("restless_moments")
        or data.get("restlessMoments")
        or data.get("restlessMomentCount")
    )
    if restless is not None:
        result["restless_moments"] = restless

    for target, keys in (
        (
            "sleep_latency",
            (
                "sleepLatencyInSeconds",
                "sleepLatencySeconds",
                "timeToFallAsleepSeconds",
                "sleep_latency",
                "sleepLatency",
                "timeToFallAsleep",
            ),
        ),
    ):
        for key in keys:
            value = _coerce_float(data.get(key))
            if value is not None:
                result[target] = value
                break

    sleep_seconds = _coerce_float(data.get("sleep_time_seconds") or data.get("sleepTimeSeconds"))
    awake_seconds = _coerce_float(data.get("awake_sleep_seconds") or data.get("awakeSleepSeconds"))
    if sleep_seconds is not None and awake_seconds is not None and (sleep_seconds + awake_seconds) > 0:
        result["sleep_efficiency"] = round(sleep_seconds / (sleep_seconds + awake_seconds) * 100.0, 1)

    quality = _sleep_quality_from_score(result.get("overall_score") or result.get("sleep_score"))
    if quality is not None:
        result["sleep_quality"] = quality

    return result


def derive_sleep_phase_percents(
    *,
    deep_sleep_time: Optional[float] = None,
    light_sleep_time: Optional[float] = None,
    rem_sleep_time: Optional[float] = None,
    awake_time: Optional[float] = None,
    total_sleep_time: Optional[float] = None,
) -> Dict[str, Optional[float]]:
    """Beregn søvnfase-prosenter fra varighetskolonner (sekunder)."""
    deep = _coerce_float(deep_sleep_time) or 0.0
    light = _coerce_float(light_sleep_time) or 0.0
    rem = _coerce_float(rem_sleep_time) or 0.0
    phase_sum = deep + light + rem
    if phase_sum <= 0:
        total = _coerce_float(total_sleep_time)
        if total is None or total <= 0:
            return {}
        phase_sum = total

    result: Dict[str, Optional[float]] = {}
    if deep > 0:
        result["deep_sleep_percent"] = round(deep / phase_sum * 100.0, 1)
    if light > 0:
        result["light_sleep_percent"] = round(light / phase_sum * 100.0, 1)
    if rem > 0:
        result["rem_sleep_percent"] = round(rem / phase_sum * 100.0, 1)

    awake = _coerce_float(awake_time)
    if awake is not None and awake >= 0:
        denom = phase_sum + awake
        if denom > 0:
            result["awake_percent"] = round(awake / denom * 100.0, 1)

    return result


def derive_sleep_efficiency(
    *,
    total_sleep_time: Optional[float] = None,
    awake_time: Optional[float] = None,
) -> Optional[float]:
    """Søvneffektivitet = total søvn / (total søvn + våken tid)."""
    total = _coerce_float(total_sleep_time)
    awake = _coerce_float(awake_time)
    if total is None or total <= 0 or awake is None or awake < 0:
        return None
    time_in_bed = total + awake
    if time_in_bed <= 0:
        return None
    return round(total / time_in_bed * 100.0, 1)


def derive_sleep_fields_from_row(row: Any) -> Dict[str, Any]:
    """
    Samler alle trygge lokale utledninger for en Sleep-rad.
    Returnerer kun felter som kan settes uten å overskrive eksisterende verdier i caller.
    """
    derived: Dict[str, Any] = {}

    if getattr(row, "sleep_score", None) is None:
        overall = getattr(row, "overall_score", None)
        if overall is not None:
            derived["sleep_score"] = overall

    phase_fields = derive_sleep_phase_percents(
        deep_sleep_time=getattr(row, "deep_sleep_time", None),
        light_sleep_time=getattr(row, "light_sleep_time", None),
        rem_sleep_time=getattr(row, "rem_sleep_time", None),
        awake_time=getattr(row, "awake_time", None),
        total_sleep_time=getattr(row, "total_sleep_time", None),
    )
    derived.update(phase_fields)

    if getattr(row, "sleep_efficiency", None) is None:
        efficiency = derive_sleep_efficiency(
            total_sleep_time=getattr(row, "total_sleep_time", None),
            awake_time=getattr(row, "awake_time", None),
        )
        if efficiency is not None:
            derived["sleep_efficiency"] = efficiency

    if getattr(row, "sleep_quality", None) is None:
        score = getattr(row, "overall_score", None) or getattr(row, "sleep_score", None)
        quality = _sleep_quality_from_score(_coerce_float(score))
        if quality is not None:
            derived["sleep_quality"] = quality

    detailed = getattr(row, "detailed_sleep_data", None)
    if isinstance(detailed, dict):
        derived.update(extract_sleep_fields_from_detailed_data(detailed))

    return derived
