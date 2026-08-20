"""Aggreger recorded prospective outcomes for ranking — aldri rekonstruert backtest som primærkilde."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..database.models.activity import Activity
from ..database.models.coaching_v5 import RecommendationExecution, RecommendationRecord
from .athlete_feedback_service import AthleteFeedbackService

MIN_SAMPLES = 8


class ProspectiveOutcomeLookup:
    def __init__(self, db: Session):
        self.db = db
        self._feedback = AthleteFeedbackService(db)

    def historical_by_type(self, *, as_of: Optional[date] = None) -> Dict[str, Any]:
        """Kun ledger-rader før as_of. Rekonstruerte backtester inngår ikke."""
        query = self.db.query(RecommendationRecord)
        if as_of is not None:
            query = query.filter(RecommendationRecord.as_of_date < as_of)
        rows = query.all()
        buckets: Dict[str, Dict[str, Any]] = {}
        for record in rows:
            wtype = record.recommended_workout_type
            bucket = buckets.setdefault(wtype, {"scores": [], "n": 0})
            execution = (
                self.db.query(RecommendationExecution)
                .filter(RecommendationExecution.recommendation_id == record.id)
                .order_by(RecommendationExecution.linked_at.desc())
                .first()
            )
            if execution is None:
                continue
            if as_of is not None and execution.activity_id:
                activity = (
                    self.db.query(Activity)
                    .filter(Activity.activity_id == execution.activity_id)
                    .first()
                )
                if activity and activity.start_time and activity.start_time.date() > as_of:
                    continue
            score = 50.0
            if execution.execution_status == "followed":
                score += 15
            elif execution.execution_status == "modified":
                score += 5
            elif execution.execution_status == "skipped":
                score -= 10
            if execution.overall_adherence is not None:
                score = 0.6 * score + 0.4 * (float(execution.overall_adherence) * 100)
            if execution.activity_id:
                fb = self._feedback.get_for_activity(execution.activity_id)
                if fb:
                    if fb.get("pain") is not None and fb["pain"] >= 5:
                        score -= 15
                    if fb.get("rpe") is not None and fb["rpe"] >= 9:
                        score -= 8
            bucket["scores"].append(max(0.0, min(100.0, score)))
            bucket["n"] += 1

        result: Dict[str, Any] = {}
        for wtype, bucket in buckets.items():
            n = bucket["n"]
            if n == 0:
                continue
            value = sum(bucket["scores"]) / n
            confidence = min(0.85, n / 20.0)
            result[wtype] = {
                "value": round(value, 1),
                "sample_count": n,
                "confidence": round(confidence, 2),
                "source": "prospective_records",
                "usable": n >= MIN_SAMPLES,
            }
        return result
