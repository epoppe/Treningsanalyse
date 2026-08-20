"""Sammenlign v3-regelkaskade mot v4 ranking uten fremtidslekkasje."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..storage import DataStorage
from .coaching_backtest_service import CoachingBacktestService
from .next_best_workout_service import NextBestWorkoutService
from .ppap_metrics_service import PpapMetricsService


class CoachingBacktestV4Service:
    def __init__(
        self,
        db: Session,
        storage: Optional[DataStorage] = None,
        goal: Optional[Dict[str, Any]] = None,
    ):
        self.db = db
        self.storage = storage
        self._goal = goal
        self._ppap = PpapMetricsService(db, storage)
        self._legacy = CoachingBacktestService(db, storage)
        self._next = NextBestWorkoutService(db, storage, self._ppap, goal=goal)

    def compare_period(
        self,
        *,
        start_date: date,
        end_date: date,
        step_days: int = 7,
        goal: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        old = self._legacy.evaluate_period(start_date=start_date, end_date=end_date, step_days=step_days)
        v4_rows = []
        current = start_date
        while current <= end_date:
            cascade = self._next.recommend(current, engine="cascade", goal=goal or self._goal)
            ranked = self._next.recommend(current, engine="ranked", goal=goal or self._goal)
            v4_rows.append(
                {
                    "as_of_date": current.isoformat(),
                    "cascade_workout": cascade.get("workout_type"),
                    "ranked_workout": ranked.get("workout_type"),
                    "decision_engine": ranked.get("decision_engine"),
                    "evidence_strength": ranked.get("evidence_strength"),
                    "recommendation_confidence": ranked.get("recommendation_confidence"),
                    "phase": (ranked.get("training_phase") or {}).get("phase"),
                    "prescription_type": (ranked.get("workout_prescription") or {}).get("workout_type"),
                    "personalized_thresholds": self._personalized_count(ranked),
                }
            )
            current += timedelta(days=step_days)

        agree = 0
        for row in v4_rows:
            if row["cascade_workout"] == row["ranked_workout"]:
                agree += 1
        n = len(v4_rows) or 1
        return {
            "old_model": old.get("summary"),
            "v4_model": {
                "evaluations": v4_rows,
                "cascade_ranked_agreement": round(agree / n, 3),
                "n": len(v4_rows),
            },
            "difference": {
                "agreement_rate": round(agree / n, 3),
                "note": "Agreement is not superiority. Do not declare v4 better without outcome data.",
            },
            "evidence": {
                "old_summary": old.get("summary"),
                "sample_dates": [r["as_of_date"] for r in v4_rows],
            },
        }

    @staticmethod
    def _personalized_count(recommendation: Dict[str, Any]) -> int:
        count = 0
        for item in recommendation.get("decision_trace") or []:
            if item.get("threshold_source") == "personalized":
                count += 1
        return count
