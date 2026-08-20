"""Enkel lastfordeling for styrke/sykkel/svømming/annet. Ikke komplette idrettsmodeller."""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..database.models.activity import Activity

CYCLING_KEYS = {
    "cycling",
    "road_biking",
    "mountain_biking",
    "indoor_cycling",
    "virtual_ride",
    "gravel_cycling",
}
SWIM_KEYS = {"lap_swimming", "open_water_swimming", "swimming"}
STRENGTH_KEYS = {"strength_training", "indoor_cardio", "hiit", "weight_training"}
RACKET_KEYS = {"tennis", "pickleball", "squash", "badminton", "paddle"}


class CrossTrainingLoadService:
    def __init__(self, db: Optional[Session] = None):
        self.db = db

    def analyze(self, activity: Activity) -> Dict[str, Any]:
        type_key = (activity.activity_type.type_key if activity.activity_type else "") or ""
        type_key = type_key.lower()
        duration_min = (float(activity.duration) / 60.0) if activity.duration else 0.0
        te = float(activity.total_training_effect or 0)
        tss = float(activity.training_stress_score or activity.epoc or 0)
        hard = te >= 3.5 or tss >= 70 or duration_min >= 75
        modality = self._modality(type_key)
        if modality == "running":
            return {
                "modality": "running",
                "cardiovascular_load": "high" if hard else "moderate",
                "running_specific_load": "high" if hard else "moderate",
                "musculoskeletal_load": "high" if hard else "moderate",
                "interference": {
                    "next_hard_run": "stacked_running_load" if hard else "low",
                },
            }
        if modality == "cycling":
            cardio = "high" if hard else ("moderate" if duration_min >= 40 else "low")
            return {
                "modality": "cycling",
                "cardiovascular_load": cardio,
                "running_specific_load": "low",
                "musculoskeletal_load": "moderate" if hard else "low",
                "interference": {
                    "threshold": "cardio_fatigue" if hard else "low",
                    "vo2_intervals": "cardio_fatigue" if hard else "low",
                    "easy_run": "low",
                },
                "note": "Hard cycling raises cardiovascular fatigue more than running-specific mechanical load.",
            }
        if modality == "strength":
            heavy_legs = "leg" in (activity.activity_name or "").lower() or te >= 3.0 or duration_min >= 40
            return {
                "modality": "strength",
                "cardiovascular_load": "moderate" if hard else "low",
                "running_specific_load": "low",
                "musculoskeletal_load": "high" if heavy_legs else "moderate",
                "interference": {
                    "threshold": "musculoskeletal" if heavy_legs else "low",
                    "vo2_intervals": "musculoskeletal" if heavy_legs else "low",
                    "easy_run": "low",
                },
                "note": "Heavy leg strength can interfere with hard running the next day without matching run-specific load.",
            }
        if modality == "swimming":
            return {
                "modality": "swimming",
                "cardiovascular_load": "low" if duration_min < 50 and te < 3.0 else "moderate",
                "running_specific_load": "low",
                "musculoskeletal_load": "low",
                "interference": {
                    "threshold": "low",
                    "vo2_intervals": "low",
                    "easy_run": "recovery_compatible",
                },
                "note": "Easy swimming is treated as recovery-compatible cross-training.",
            }
        return {
            "modality": modality,
            "cardiovascular_load": "moderate" if hard else "low",
            "running_specific_load": "low",
            "musculoskeletal_load": "moderate" if modality in {"tennis", "other"} and hard else "low",
            "interference": {"threshold": "unspecified", "vo2_intervals": "unspecified", "easy_run": "low"},
        }

    @staticmethod
    def _modality(type_key: str) -> str:
        if type_key in CYCLING_KEYS or "cycl" in type_key or "bik" in type_key:
            return "cycling"
        if type_key in SWIM_KEYS or "swim" in type_key:
            return "swimming"
        if type_key in STRENGTH_KEYS or "strength" in type_key:
            return "strength"
        if type_key in RACKET_KEYS or "tennis" in type_key:
            return "tennis"
        if "run" in type_key:
            return "running"
        return "other"
