"""Sammenlign planlagte ukeøkter med faktisk gjennomføring — observasjonelt, ikke moraliserende."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from ..database.models.activity import Activity
from ..database.models.coaching_v5 import RecommendationExecution, RecommendationRecord
from ..utils.activity_filters import is_running_activity
from .session_classifier_service import SessionClassifierService


class PlanVsActualService:
    def __init__(self, db: Session, storage=None):
        self.db = db
        self._classifier = SessionClassifierService(db, storage)

    def compare(
        self,
        plan: Dict[str, Any],
        *,
        week_start: Optional[date] = None,
    ) -> Dict[str, Any]:
        week_start = week_start or self._resolve_week_start(plan)
        sessions = plan.get("sessions") or []
        days: List[Dict[str, Any]] = []

        for session in sessions:
            offset = int(session.get("day_offset") or 0)
            day_date = week_start + timedelta(days=offset)
            actual = self._actual_for_day(day_date)
            planned_type = session.get("type")
            actual_type = actual.get("type")
            status = self._match_status(planned_type, actual_type, actual.get("execution_status"))
            days.append(
                {
                    "date": day_date.isoformat(),
                    "day_offset": offset,
                    "weekday": day_date.weekday(),
                    "planned_type": planned_type,
                    "planned_duration_min": session.get("duration_min"),
                    "actual_type": actual_type,
                    "actual_duration_min": actual.get("duration_min"),
                    "execution_status": actual.get("execution_status") or status,
                    "activity_id": actual.get("activity_id"),
                    "activity_name": actual.get("activity_name"),
                    "adherence": actual.get("adherence"),
                }
            )

        return {
            "week_start": week_start.isoformat(),
            "days": days,
            "summary": self._summarize(days),
        }

    @staticmethod
    def _resolve_week_start(plan: Dict[str, Any]) -> date:
        raw = plan.get("week_start")
        if raw:
            try:
                return date.fromisoformat(str(raw))
            except ValueError:
                pass
        return date.today()

    def _actual_for_day(self, day_date: date) -> Dict[str, Any]:
        exec_row = (
            self.db.query(RecommendationExecution)
            .join(RecommendationRecord, RecommendationExecution.recommendation_id == RecommendationRecord.id)
            .filter(
                RecommendationRecord.as_of_date == day_date,
                RecommendationRecord.is_shadow.is_(False),
            )
            .order_by(RecommendationExecution.linked_at.desc())
            .first()
        )
        if exec_row is not None:
            activity = None
            if exec_row.activity_id:
                activity = (
                    self.db.query(Activity)
                    .filter(Activity.activity_id == exec_row.activity_id)
                    .first()
                )
            return {
                "type": exec_row.actual_type,
                "duration_min": exec_row.actual_duration,
                "execution_status": exec_row.execution_status,
                "activity_id": exec_row.activity_id,
                "activity_name": activity.activity_name if activity else None,
                "adherence": exec_row.overall_adherence,
            }

        activities = (
            self.db.query(Activity)
            .options(joinedload(Activity.activity_type))
            .filter(func.date(Activity.start_time) == day_date)
            .all()
        )
        running = [a for a in activities if is_running_activity(a)]
        if not running:
            return {}

        primary = max(running, key=lambda a: float(a.duration or 0))
        classified = self._classifier.classify_activity(primary, end_date=day_date)
        return {
            "type": classified.get("session_type"),
            "duration_min": round(float(primary.duration or 0) / 60.0, 1) if primary.duration else None,
            "execution_status": "unplanned",
            "activity_id": primary.activity_id,
            "activity_name": primary.activity_name,
            "adherence": None,
        }

    @staticmethod
    def _match_status(
        planned: Optional[str],
        actual: Optional[str],
        execution_status: Optional[str],
    ) -> str:
        if execution_status:
            return execution_status
        if not planned or planned == "rest":
            return "rest" if not actual else "unplanned"
        if not actual:
            return "missed"
        if planned == actual:
            return "followed"
        return "modified"

    @staticmethod
    def _summarize(days: List[Dict[str, Any]]) -> Dict[str, Any]:
        planned_sessions = [d for d in days if d.get("planned_type") not in {None, "rest"}]
        completed = [
            d
            for d in planned_sessions
            if d.get("execution_status") in {"followed", "modified", "completed", "partial"}
            or d.get("actual_type")
        ]
        missed = [d for d in planned_sessions if d.get("execution_status") == "missed"]
        return {
            "planned_count": len(planned_sessions),
            "completed_count": len(completed),
            "missed_count": len(missed),
            "completion_rate": round(len(completed) / len(planned_sessions), 2) if planned_sessions else None,
        }
