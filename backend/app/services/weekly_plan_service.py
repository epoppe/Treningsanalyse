"""Rullerende 7-dagers plan — availability-aware via WeeklyPlanOptimizer."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..storage import DataStorage
from .ppap_metrics_service import PpapMetricsService
from .training_plan_store import TrainingPlanStore
from .weekly_plan_optimizer import WeeklyPlanOptimizer

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
        self._optimizer = WeeklyPlanOptimizer(db, storage, self._ppap, goal=goal)
        self._store = TrainingPlanStore(db)

    def build(
        self,
        day: Optional[date] = None,
        *,
        goal: Optional[Dict[str, Any]] = None,
        include_treadmill: bool = False,
        persist: bool = False,
        next_rec: Optional[Dict[str, Any]] = None,
        previous_plan_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        day = day or date.today()
        payload = self._optimizer.optimize(
            day,
            goal=goal,
            include_treadmill=include_treadmill,
            next_rec=next_rec,
        )
        if persist:
            stored = self._store.persist_new_plan(
                week_start=day,
                payload=payload,
                previous_plan_id=previous_plan_id,
            )
            payload["plan_id"] = stored["plan_id"]
            payload["version"] = stored["version"]
            payload["previous_plan_id"] = stored["previous_plan_id"]
        else:
            payload.setdefault("plan_id", None)
            payload.setdefault("version", None)
        return payload
