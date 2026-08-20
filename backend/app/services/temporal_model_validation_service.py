"""Expanding-window / walk-forward validation — no random train/test split."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..storage import DataStorage
from .coaching_baselines import CoachingBaselines
from .next_best_workout_service import NextBestWorkoutService
from .ppap_metrics_service import PpapMetricsService
from .recommendation_outcome_service import RecommendationOutcomeService
from .statistical_uncertainty import bootstrap_ci, evidence_band


class TemporalModelValidationService:
    def __init__(self, db: Session, storage: Optional[DataStorage] = None):
        self.db = db
        self.storage = storage
        self._ppap = PpapMetricsService(db, storage)
        self._baselines = CoachingBaselines(db, storage, self._ppap)

    def walk_forward(
        self,
        *,
        start_date: date,
        end_date: date,
        min_train_days: int = 60,
        step_days: int = 30,
    ) -> Dict[str, Any]:
        folds: List[Dict[str, Any]] = []
        cursor = start_date + timedelta(days=min_train_days)
        while cursor <= end_date:
            train_end = cursor - timedelta(days=1)
            test_day = cursor
            fold = self._evaluate_fold(start_date, train_end, test_day)
            folds.append(fold)
            cursor += timedelta(days=step_days)

        model_hits = [f["model_match"] for f in folds if f.get("model_match") is not None]
        baseline_hits = [f["baseline_match"] for f in folds if f.get("baseline_match") is not None]
        model_rate = sum(model_hits) / len(model_hits) if model_hits else None
        baseline_rate = sum(baseline_hits) / len(baseline_hits) if baseline_hits else None
        delta = None
        if model_rate is not None and baseline_rate is not None:
            delta = round(model_rate - baseline_rate, 3)
        return {
            "validation_type": "walk_forward",
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "folds": folds,
            "aggregate": {
                "fold_count": len(folds),
                "model_metric": model_rate,
                "baseline_metric": baseline_rate,
                "delta": delta,
                "note": "Do not declare model better without positive out-of-sample delta.",
            },
        }

    def _evaluate_fold(self, train_start: date, train_end: date, test_day: date) -> Dict[str, Any]:
        # Model and baseline recommendations as-of test_day (no future leakage in recommend()).
        model = NextBestWorkoutService(self.db, self.storage, self._ppap).recommend(test_day)
        baseline = self._baselines.workout_recommendation(test_day)
        outcome = RecommendationOutcomeService(self.db, self.storage).simulate_as_of(test_day)
        actual = outcome.get("actual")
        model_match = None
        baseline_match = None
        if actual is not None:
            model_match = self._compatible(model.get("workout_type"), actual)
            baseline_match = self._compatible(baseline.get("workout_type"), actual)
        readiness_b = self._baselines.readiness_baseline(test_day)
        return {
            "train_start": train_start.isoformat(),
            "train_end": train_end.isoformat(),
            "test_date": test_day.isoformat(),
            "model_recommendation": model.get("workout_type"),
            "baseline_recommendation": baseline.get("workout_type"),
            "actual": actual,
            "model_match": model_match,
            "baseline_match": baseline_match,
            "readiness_baseline": readiness_b,
            "evaluation_kind": "backtest",
            "no_future_leakage": True,
        }

    @staticmethod
    def _compatible(recommended: Optional[str], actual: Optional[str]) -> Optional[bool]:
        if recommended is None or actual is None:
            return None
        mapping = {
            "easy_run": {"easy_aerobic", "recovery_run", "steady", "long_aerobic"},
            "recovery_run": {"recovery_run", "easy_aerobic"},
            "long_run": {"long_aerobic", "easy_aerobic"},
            "threshold": {"threshold", "tempo", "steady"},
            "vo2_intervals": {"vo2_intervals", "anaerobic"},
            "race_pace": {"race", "threshold", "tempo"},
            "rest": set(),
        }
        return actual in mapping.get(recommended, set()) or actual == recommended
