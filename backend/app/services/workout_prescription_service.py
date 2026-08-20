"""Konkret øktpreskripsjon fra workout type + intensitet + fase."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..storage import DataStorage
from .intensity_prescription_service import IntensityPrescriptionService
from .ppap_metrics_service import PpapMetricsService

TEMPLATES: Dict[str, Dict[str, Any]] = {
    "rest": {
        "title": "Rest day",
        "warmup": None,
        "main_set": None,
        "cooldown_min": 0,
        "total_duration_min": 0,
        "stimulus": "recovery",
    },
    "recovery_run": {
        "title": "30–40 min recovery jog",
        "warmup": {"duration_min": 5, "intensity": "easy"},
        "main_set": {
            "repetitions": 1,
            "work_duration_min": 30,
            "recovery_duration_min": 0,
            "recovery_type": None,
        },
        "cooldown_min": 5,
        "total_duration_min": 40,
        "stimulus": "restore aerobic circulation",
    },
    "easy_run": {
        "title": "Easy aerobic run",
        "warmup": {"duration_min": 5, "intensity": "easy"},
        "main_set": {
            "repetitions": 1,
            "work_duration_min": 50,
            "recovery_duration_min": 0,
            "recovery_type": None,
        },
        "cooldown_min": 5,
        "total_duration_min": 55,
        "stimulus": "aerobic volume",
    },
    "long_run": {
        "title": "Long aerobic run",
        "warmup": {"duration_min": 10, "intensity": "easy"},
        "main_set": {
            "repetitions": 1,
            "work_duration_min": 90,
            "recovery_duration_min": 0,
            "recovery_type": None,
        },
        "cooldown_min": 10,
        "total_duration_min": 110,
        "stimulus": "durability / aerobic endurance",
    },
    "steady": {
        "title": "40 min steady aerobic",
        "warmup": {"duration_min": 10, "intensity": "easy"},
        "main_set": {
            "repetitions": 1,
            "work_duration_min": 40,
            "recovery_duration_min": 0,
            "recovery_type": None,
        },
        "cooldown_min": 8,
        "total_duration_min": 58,
        "stimulus": "high-end aerobic",
    },
    "threshold": {
        "title": "3 x 10 min controlled threshold",
        "warmup": {"duration_min": 15, "intensity": "easy"},
        "main_set": {
            "repetitions": 3,
            "work_duration_min": 10,
            "recovery_duration_min": 2,
            "recovery_type": "easy_jog",
        },
        "cooldown_min": 10,
        "total_duration_min": 59,
        "stimulus": "LT2 development",
    },
    "vo2_intervals": {
        "title": "5 x 3 min VO2 intervals",
        "warmup": {"duration_min": 15, "intensity": "easy"},
        "main_set": {
            "repetitions": 5,
            "work_duration_min": 3,
            "recovery_duration_min": 2.5,
            "recovery_type": "easy_jog",
        },
        "cooldown_min": 10,
        "total_duration_min": 52,
        "stimulus": "VO2max development",
    },
    "race_pace": {
        "title": "3 x 8 min race-pace",
        "warmup": {"duration_min": 15, "intensity": "easy"},
        "main_set": {
            "repetitions": 3,
            "work_duration_min": 8,
            "recovery_duration_min": 2,
            "recovery_type": "easy_jog",
        },
        "cooldown_min": 10,
        "total_duration_min": 55,
        "stimulus": "race-specific pace",
    },
    "strides": {
        "title": "Easy run + 6 x 20s strides",
        "warmup": {"duration_min": 10, "intensity": "easy"},
        "main_set": {
            "repetitions": 6,
            "work_duration_min": 0.33,
            "recovery_duration_min": 1,
            "recovery_type": "walk_jog",
        },
        "cooldown_min": 5,
        "total_duration_min": 45,
        "stimulus": "neuromuscular / form",
    },
}

PHASE_THRESHOLD_OVERRIDE = {
    "base": {"repetitions": 2, "work_duration_min": 8, "title": "2 x 8 min controlled threshold"},
    "build": {"repetitions": 3, "work_duration_min": 10, "title": "3 x 10 min controlled threshold"},
    "specific": {"repetitions": 3, "work_duration_min": 12, "title": "3 x 12 min controlled threshold"},
    "peak": {"repetitions": 2, "work_duration_min": 10, "title": "2 x 10 min controlled threshold"},
    "taper": {"repetitions": 2, "work_duration_min": 6, "title": "2 x 6 min controlled threshold"},
    "recovery": None,
}


class WorkoutPrescriptionService:
    def __init__(
        self,
        db: Session,
        storage: Optional[DataStorage] = None,
        ppap: Optional[PpapMetricsService] = None,
    ):
        self.db = db
        self.storage = storage
        self._ppap = ppap or PpapMetricsService(db, storage)
        self._intensity = IntensityPrescriptionService(db, storage, self._ppap)

    def prescribe(
        self,
        workout_type: str,
        *,
        day: Optional[date] = None,
        phase: Optional[str] = None,
        include_treadmill: bool = False,
    ) -> Dict[str, Any]:
        day = day or date.today()
        template = dict(TEMPLATES.get(workout_type, TEMPLATES["easy_run"]))
        if workout_type == "threshold" and phase in PHASE_THRESHOLD_OVERRIDE:
            override = PHASE_THRESHOLD_OVERRIDE[phase]
            if override is None:
                workout_type = "easy_run"
                template = dict(TEMPLATES["easy_run"])
            else:
                template["title"] = override["title"]
                main = dict(template["main_set"])
                main["repetitions"] = override["repetitions"]
                main["work_duration_min"] = override["work_duration_min"]
                template["main_set"] = main
                work = override["repetitions"] * override["work_duration_min"]
                rec = override["repetitions"] * 2
                template["total_duration_min"] = 15 + work + rec + 10

        intensity = self._intensity.prescribe(
            workout_type,
            end_date=day,
            include_treadmill=include_treadmill,
        )
        main = template.get("main_set")
        if isinstance(main, dict):
            main = {
                **main,
                "target_hr": intensity.get("hr_bpm"),
                "target_pace_sec_km": intensity.get("pace_sec_km"),
                "target_power_w": intensity.get("power_w"),
                "target_rpe": intensity.get("rpe"),
                "intensity_source": intensity.get("source"),
            }
            template["main_set"] = main

        if intensity.get("confidence", 0) < 0.45:
            if main and main.get("target_pace_sec_km"):
                main["target_pace_sec_km"] = None
                main["pace_omitted_reason"] = "threshold_confidence_low"
            template["limitations"] = list(intensity.get("limitations") or []) + ["prefer_hr_or_rpe"]

        return {
            "workout_type": workout_type,
            **template,
            "confidence": intensity.get("confidence"),
            "intensity": {
                "source": intensity.get("source"),
                "zone": intensity.get("zone"),
                "limitations": intensity.get("limitations"),
            },
        }
