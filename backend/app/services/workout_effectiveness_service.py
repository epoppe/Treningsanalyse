"""Historisk respons etter økttyper — observational, as-of-safe, ikke kausalitet."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session, joinedload

from ..database.models.activity import Activity
from ..storage import DataStorage
from ..utils.activity_filters import is_running_activity
from .metric_evidence import confidence_from_sample_count
from .ppap_metrics_service import PpapMetricsService
from .session_classifier_service import SessionClassifierService
from .training_response_service import TrainingResponseService

LAGS = (7, 21, 42)
WORKOUT_GROUPS = {
    "threshold": {"tempo", "threshold"},
    "vo2_intervals": {"vo2_intervals", "anaerobic"},
    "long_run": {"long_aerobic"},
    "easy_volume": {"recovery_run", "easy_aerobic", "steady"},
}


class WorkoutEffectivenessService:
    def __init__(
        self,
        db: Session,
        storage: Optional[DataStorage] = None,
        ppap: Optional[PpapMetricsService] = None,
    ):
        self.db = db
        self.storage = storage
        self._ppap = ppap or PpapMetricsService(db, storage)
        self._classifier = SessionClassifierService(db, storage)
        self._response = TrainingResponseService(db, storage, self._ppap)

    def analyze(
        self,
        workout_type: str,
        *,
        end_date: Optional[date] = None,
        lookback_days: int = 365,
    ) -> Dict[str, Any]:
        end = end_date or date.today()
        start = end - timedelta(days=lookback_days)
        types = WORKOUT_GROUPS.get(workout_type, {workout_type})
        activities = (
            self.db.query(Activity)
            .options(joinedload(Activity.activity_type))
            .filter(
                and_(
                    func.date(Activity.start_time) >= start,
                    func.date(Activity.start_time) <= end,
                )
            )
            .all()
        )
        sessions: List[date] = []
        for activity in activities:
            if not is_running_activity(activity) or not activity.start_time:
                continue
            day = activity.start_time.date()
            st = self._classifier.classify_activity(activity, end_date=day).get("session_type")
            if st in types:
                sessions.append(day)

        historical: Dict[str, Any] = {}
        samples = 0
        for lag in LAGS:
            deltas: List[float] = []
            for session_day in sessions:
                outcome_day = session_day + timedelta(days=lag)
                if outcome_day > end:
                    continue
                before = self._response._outcome_value("threshold_pace", session_day)
                after = self._response._outcome_value("threshold_pace", outcome_day)
                if before is not None and after is not None:
                    # pace: negative delta = faster = favorable
                    deltas.append(after - before)
            historical[f"{lag}d"] = {
                "mean_threshold_pace_change_sec_km": round(sum(deltas) / len(deltas), 2) if deltas else None,
                "sample_count": len(deltas),
            }
            samples += len(deltas)

        confidence = confidence_from_sample_count(samples, min_samples=4, target_samples=20)
        return {
            "workout_type": workout_type,
            "historical_response": historical,
            "sample_count": samples,
            "confidence": round(confidence, 2),
            "disclaimer": "Observational association with lag windows — not a causal effect. Total load is not fully controlled.",
        }

    def summary_scores(self, end_date: Optional[date] = None) -> Dict[str, float]:
        """Kompakt 0–100 for ranking (høyere = historisk mer favorable pace-endring)."""
        scores: Dict[str, float] = {}
        for wtype in ("threshold", "vo2_intervals", "long_run", "easy_volume"):
            result = self.analyze(wtype, end_date=end_date)
            lag = (result.get("historical_response") or {}).get("21d") or {}
            change = lag.get("mean_threshold_pace_change_sec_km")
            if change is None:
                continue
            scores[wtype] = max(0.0, min(100.0, 50.0 - float(change) * 2.0))
        if "easy_volume" in scores:
            scores["easy_run"] = scores["easy_volume"]
        return scores
