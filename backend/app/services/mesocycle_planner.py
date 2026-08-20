"""4–6 week mesocycle sketch — not a rigid session calendar."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..storage import DataStorage
from .deload_need_service import DeloadNeedService
from .goal_context_service import GoalContextService
from .ppap_metrics_service import PpapMetricsService
from .training_phase_service import TrainingPhaseService


class MesocyclePlanner:
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
        self._goals = GoalContextService(db, storage, self._ppap, goal=goal)
        self._phase = TrainingPhaseService(db, storage, self._ppap, goal=goal)
        self._deload = DeloadNeedService(db, storage, self._ppap)

    def plan(
        self,
        start: Optional[date] = None,
        *,
        weeks: int = 5,
        goal: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        start = start or date.today()
        weeks = max(4, min(6, weeks))
        goal_ctx = self._goals.build(start, goal=goal)
        rows: List[Dict[str, Any]] = []
        for i in range(weeks):
            week_start = start + timedelta(days=7 * i)
            phase = self._phase.determine(week_start, goal=goal)
            deload = self._deload.assess(week_start)
            phase_name = phase.get("phase") or "maintenance"
            volume = self._volume(phase_name, deload.get("deload_need"))
            quality = 0 if deload.get("deload_need") == "recommended" else (2 if phase_name in {"build", "specific"} else 1)
            primary, secondary = self._stimuli(phase_name, goal_ctx)
            long_run = [70, 110] if goal_ctx.get("target_event") in {"half_marathon", "marathon"} else [50, 80]
            if phase_name in {"taper", "recovery"} or deload.get("deload_need") == "recommended":
                long_run = [40, 70]
            rows.append(
                {
                    "week_index": i + 1,
                    "week_start": week_start.isoformat(),
                    "volume_target_min": volume,
                    "quality_sessions": quality,
                    "long_run_target_min": long_run,
                    "primary_stimulus": primary,
                    "secondary_stimulus": secondary,
                    "deload_state": deload.get("deload_need"),
                    "phase": phase_name,
                    "confidence": round(min(0.8, float(phase.get("confidence") or 0.5)), 2),
                }
            )
        return {
            "start": start.isoformat(),
            "weeks": weeks,
            "goal": goal_ctx,
            "mesocycle": rows,
            "note": "Weekly targets only — not a rigid day-by-day calendar.",
        }

    @staticmethod
    def _volume(phase: str, deload: Optional[str]) -> List[int]:
        if deload == "recommended" or phase == "recovery":
            return [90, 160]
        if phase == "taper":
            return [100, 180]
        if phase in {"build", "specific"}:
            return [220, 320]
        if phase == "peak":
            return [180, 260]
        return [160, 240]

    @staticmethod
    def _stimuli(phase: str, goal: Dict[str, Any]) -> tuple:
        event = goal.get("target_event")
        if phase == "taper":
            return "race_pace", "easy_volume"
        if phase == "recovery":
            return "easy_volume", None
        if event in {"5k", "10k"}:
            return "vo2_intervals", "threshold"
        if event in {"half_marathon", "marathon"}:
            return "threshold", "long_run"
        return "easy_volume", "threshold"
