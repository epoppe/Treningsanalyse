"""Rullerende 7-dagers plan — foreløpig, ikke rigid kalender."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..storage import DataStorage
from .next_best_workout_service import NextBestWorkoutService
from .ppap_metrics_service import PpapMetricsService
from .workout_prescription_service import WorkoutPrescriptionService

PHASE_HARD_BUDGET = {
    "recovery": 0,
    "base": 1,
    "build": 1,
    "specific": 2,
    "peak": 1,
    "taper": 1,
    "maintenance": 1,
}


class WeeklyPlanService:
    def __init__(
        self,
        db: Session,
        storage: Optional[DataStorage] = None,
        ppap: Optional[PpapMetricsService] = None,
        goal: Optional[Dict[str, Any]] = None,
    ):
        self.db = db
        self.storage = storage
        self._ppap = ppap or PpapMetricsService(db, storage)
        self._next = NextBestWorkoutService(db, storage, self._ppap, goal=goal)
        self._prescription = WorkoutPrescriptionService(db, storage, self._ppap)

    def build(
        self,
        day: Optional[date] = None,
        *,
        goal: Optional[Dict[str, Any]] = None,
        include_treadmill: bool = False,
    ) -> Dict[str, Any]:
        day = day or date.today()
        next_rec = self._next.recommend(day, include_treadmill=include_treadmill, goal=goal)
        phase = (next_rec.get("training_phase") or {}).get("phase") or "maintenance"
        hard_budget = PHASE_HARD_BUDGET.get(phase, 1)
        params = (next_rec.get("decision_trace") or [])
        spacing_hours = 36.0
        for item in params:
            if item.get("factor") == "hard_session_spacing" and item.get("threshold"):
                spacing_hours = float(item["threshold"])
                break
        spacing_days = max(1, int(round(spacing_hours / 24.0)))

        sessions: List[Dict[str, Any]] = []
        hard_placed = 0
        next_hard_offset = None
        first = next_rec.get("workout_type")
        sessions.append(self._session(0, first, next_rec.get("workout_prescription"), next_rec.get("duration_min")))
        if first in {"threshold", "vo2_intervals", "race_pace"}:
            hard_placed += 1
            next_hard_offset = spacing_days

        event = (next_rec.get("goal") or {}).get("target_event")
        long_offset = 5 if event in {"half_marathon", "marathon"} else None
        if phase == "recovery":
            long_offset = None

        for offset in range(1, 7):
            if first == "rest" and offset == 1:
                sessions.append(self._easy(offset, phase))
                continue
            if long_offset is not None and offset == long_offset and first != "long_run":
                sessions.append(
                    self._session(
                        offset,
                        "long_run",
                        self._prescription.prescribe("long_run", day=day, phase=phase),
                        [80, 120],
                    )
                )
                continue
            if (
                hard_placed < hard_budget
                and next_hard_offset is not None
                and offset >= next_hard_offset
                and offset not in {3, 6}
            ):
                wtype = "threshold" if phase != "taper" else "race_pace"
                sessions.append(
                    self._session(
                        offset,
                        wtype,
                        self._prescription.prescribe(wtype, day=day, phase=phase),
                        [45, 60],
                    )
                )
                hard_placed += 1
                next_hard_offset = offset + spacing_days
                continue
            if offset in {3, 6}:
                sessions.append({"day_offset": offset, "type": "rest", "duration_min": [0, 0], "prescription": None})
                continue
            sessions.append(self._easy(offset, phase, day))

        target_lo = 180 if phase != "taper" else 120
        target_hi = 280 if phase in {"build", "specific"} else 230
        if phase == "recovery":
            target_lo, target_hi = 90, 160

        objective = {
            "recovery": "restore and easy circulation only",
            "base": "aerobic volume + optional strides",
            "build": "aerobic volume + one threshold stimulus",
            "specific": "race-specific work + durability",
            "peak": "sharpen and protect freshness",
            "taper": "reduce load, keep race-pace reminders",
            "maintenance": "keep aerobic volume + one quality session",
        }.get(phase, "aerobic volume + one threshold stimulus")

        return {
            "week_start": day.isoformat(),
            "week_objective": objective,
            "sessions": sessions,
            "target_volume_min": [target_lo, target_hi],
            "hard_sessions": hard_placed,
            "confidence": round(min(0.85, float(next_rec.get("recommendation_confidence") or 0.5)), 2),
            "adaptation_rules": [
                "If HRV drops beyond calibrated warning, delay quality 24–48h",
                "If RHR rises beyond calibrated warning, replace quality with easy",
                "If hard-day density is high, keep remaining days easy",
                "This is a rolling sketch — not a locked calendar",
            ],
            "phase": phase,
            "recommended_next_session": {
                "workout_type": first,
                "prescription": next_rec.get("workout_prescription"),
            },
        }

    def _easy(self, offset: int, phase: str, day: Optional[date] = None) -> Dict[str, Any]:
        wtype = "recovery_run" if phase == "recovery" else "easy_run"
        return self._session(
            offset,
            wtype,
            self._prescription.prescribe(wtype, day=day or date.today(), phase=phase),
            [35, 55] if wtype == "recovery_run" else [45, 70],
        )

    @staticmethod
    def _session(offset: int, wtype: str, prescription: Any, duration: Any) -> Dict[str, Any]:
        return {
            "day_offset": offset,
            "type": wtype,
            "duration_min": duration,
            "prescription": prescription,
        }
