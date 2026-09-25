"""Selective feedback prompt. Scoring stays in FeedbackValueService."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..database.models.activity import Activity
from ..database.models.coaching_v5 import RecommendationExecution, ShadowRecommendation
from .athlete_feedback_service import AthleteFeedbackService
from .coaching_operational_monitors import FeedbackValueService

PROMPT_MAX_AGE_DAYS = 14
_QUALITY_TYPES = {"threshold", "vo2_intervals", "race_pace", "race", "tempo"}


class FeedbackPromptService:
    """Read-only prompt decision for one activity. Repeated calls do not write."""

    def __init__(self, db: Session):
        self.db = db
        self._feedback = AthleteFeedbackService(db)
        self._value = FeedbackValueService()

    def for_activity(self, activity_id: str, *, today: Optional[date] = None) -> Dict[str, Any]:
        today = today or date.today()
        activity = (
            self.db.query(Activity)
            .filter(Activity.activity_id == str(activity_id))
            .first()
        )
        if activity is None:
            return {"status": "not_found", "activity_id": str(activity_id)}

        existing = self._feedback.get_for_activity(activity.activity_id)
        base = {
            "status": "ok",
            "activity_id": activity.activity_id,
            "already_has_feedback": existing is not None,
            "should_prompt": False,
            "priority": "none",
            "reasons": [],
        }
        if existing is not None:
            base["reasons"] = ["already_has_feedback"]
            return base

        activity_day = _activity_day(activity)
        if activity_day is None or activity_day < today - timedelta(days=PROMPT_MAX_AGE_DAYS):
            base["reasons"] = ["activity_outside_prompt_window"]
            return base

        prioritized = self._value.prioritize(context=self._context(activity, activity_day))
        priority = prioritized["feedback_priority"]
        base["priority"] = priority
        base["reasons"] = list(prioritized.get("reasons") or [])
        base["should_prompt"] = priority in {"high_value", "useful"}
        base["note"] = prioritized.get("note")
        return base

    def _context(self, activity: Activity, activity_day: date) -> Dict[str, Any]:
        execution = (
            self.db.query(RecommendationExecution)
            .filter(RecommendationExecution.activity_id == activity.activity_id)
            .order_by(RecommendationExecution.linked_at.desc())
            .first()
        )
        planned = (execution.planned_type if execution else None) or ""
        actual = (execution.actual_type if execution else None) or ""
        name = (activity.activity_name or "").lower()
        is_race = planned in {"race", "race_pace"} or actual in {"race", "race_pace"} or "race" in name
        modified_quality = bool(
            execution
            and (execution.execution_status or "") == "modified"
            and (planned in _QUALITY_TYPES or actual in _QUALITY_TYPES)
        )
        unexpected = bool(
            execution
            and execution.overall_adherence is not None
            and float(execution.overall_adherence) < 0.45
        )
        shadow = (
            self.db.query(ShadowRecommendation)
            .filter(ShadowRecommendation.as_of_date == activity_day)
            .first()
        )
        shadow_disagreement = bool(
            shadow and shadow.production_workout_type and shadow.production_workout_type != shadow.shadow_workout_type
        )
        return {
            "is_race": is_race,
            "modified_quality_session": modified_quality,
            "unexpected_execution_quality": unexpected,
            "shadow_disagreement": shadow_disagreement,
            "new_prescription": bool(execution and (execution.execution_status or "") == "replaced"),
            "unusual_recovery": False,
        }


def _activity_day(activity: Activity) -> Optional[date]:
    start = activity.start_time
    if start is None:
        return None
    if isinstance(start, datetime):
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        return start.date()
    return start
