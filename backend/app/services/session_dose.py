"""Canonical session dose — type alone is not enough."""

from __future__ import annotations

from typing import Any, Dict, Optional


def dose_from_prescription(
    workout_type: str,
    prescription: Optional[Dict[str, Any]] = None,
    *,
    duration_min: Optional[Any] = None,
) -> Dict[str, Any]:
    prescription = prescription or {}
    total = duration_min or prescription.get("total_duration_min")
    if isinstance(total, (list, tuple)) and total:
        total_duration = float(total[-1])
    elif isinstance(total, (int, float)):
        total_duration = float(total)
    else:
        total_duration = None

    main = prescription.get("main_set") or {}
    reps = main.get("repetitions")
    work = main.get("work_duration_min")
    work_duration = None
    if reps is not None and work is not None:
        work_duration = float(reps) * float(work)
    elif work is not None:
        work_duration = float(work)

    intensity = {
        "easy_run": 0.3,
        "recovery_run": 0.2,
        "long_run": 0.45,
        "threshold": 0.75,
        "vo2_intervals": 0.9,
        "race_pace": 0.8,
        "rest": 0.0,
    }.get(workout_type, 0.5)

    cv_load = None
    if work_duration is not None:
        cv_load = round(work_duration * intensity, 1)
    elif total_duration is not None:
        cv_load = round(total_duration * intensity * 0.6, 1)

    return {
        "workout_type": workout_type,
        "duration_min": total_duration,
        "work_duration_min": work_duration,
        "intensity": intensity,
        "recovery": main.get("recovery_duration_min") or main.get("rest_duration_min"),
        "mechanical_load": total_duration,
        "cardiovascular_load": cv_load,
        "dose_key": _dose_key(workout_type, work_duration, total_duration),
        "note": "3x10 threshold ≠ 5x10 threshold — dose separates type from load.",
    }


def _dose_key(workout_type: str, work: Optional[float], total: Optional[float]) -> str:
    w = int(work) if work is not None else "na"
    t = int(total) if total is not None else "na"
    return f"{workout_type}:work{w}:total{t}"
