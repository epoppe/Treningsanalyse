"""Koble faktisk aktivitet til nærmeste lagrede anbefaling — uten å likestille adherence og kvalitet."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session, joinedload

from ..database.models.activity import Activity
from ..database.models.coaching_v5 import RecommendationExecution, RecommendationRecord
from ..storage import DataStorage
from ..utils.activity_filters import is_running_activity
from .recommendation_ledger_service import RecommendationLedgerService
from .session_classifier_service import SessionClassifierService
from .workout_execution_analysis_service import WorkoutExecutionAnalysisService

COMPATIBLE = {
    "rest": set(),
    "recovery_run": {"recovery_run", "easy_aerobic"},
    "easy_run": {"easy_aerobic", "recovery_run", "steady", "long_aerobic"},
    "long_run": {"long_aerobic", "easy_aerobic"},
    "threshold": {"threshold", "tempo", "steady"},
    "vo2_intervals": {"vo2_intervals", "anaerobic"},
    "race_pace": {"race", "threshold", "tempo"},
}


class RecommendationExecutionService:
    def __init__(self, db: Session, storage: Optional[DataStorage] = None):
        self.db = db
        self.storage = storage
        self._classifier = SessionClassifierService(db, storage)
        self._ledger = RecommendationLedgerService(db)
        self._execution_quality = WorkoutExecutionAnalysisService(db, storage)

    def link_activity(self, activity: Activity, *, commit: bool = True) -> Dict[str, Any]:
        if activity.start_time is None:
            return self._store(None, activity, "unplanned", None, None, commit=commit)
        day = activity.start_time.date()
        record = (
            self.db.query(RecommendationRecord)
            .filter(
                RecommendationRecord.as_of_date == day,
                RecommendationRecord.is_active.is_(True),
            )
            .order_by(RecommendationRecord.generated_at.desc())
            .first()
        )
        if record is None:
            nearby = (
                self.db.query(RecommendationRecord)
                .filter(
                    RecommendationRecord.as_of_date >= day - timedelta(days=1),
                    RecommendationRecord.as_of_date <= day,
                )
                .order_by(RecommendationRecord.generated_at.desc())
                .first()
            )
            record = nearby

        actual_type = None
        if is_running_activity(activity, include_treadmill=True):
            actual_type = self._classifier.classify_activity(activity, end_date=day).get("session_type")
        else:
            actual_type = (activity.activity_type.type_key if activity.activity_type else "non_running")

        if record is None:
            return self._store(None, activity, "unplanned", None, actual_type, commit=commit)

        planned = record.recommended_workout_type
        planned_dur = self._planned_duration_min(record)
        actual_dur = (float(activity.duration) / 60.0) if activity.duration else None
        compatible = actual_type in COMPATIBLE.get(planned, set()) or actual_type == planned
        analysis = self._execution_quality.analyze(activity, record.workout_prescription_json or {})

        if planned == "rest":
            status = "replaced"
        elif compatible and self._duration_close(planned_dur, actual_dur) and analysis.get("completion_pct", 100) >= 80:
            status = "followed"
        elif compatible:
            status = "modified"
        else:
            status = "replaced"

        intensity = {
            "target_intensity_pct": analysis.get("target_intensity_pct"),
            "note": "Adherence is not session quality.",
        }
        structure = {
            "completion_pct": analysis.get("completion_pct"),
            "interval_consistency": analysis.get("interval_consistency"),
        }
        overall = None
        parts = [p for p in (analysis.get("completion_pct"), analysis.get("target_intensity_pct")) if p is not None]
        if parts:
            overall = round(sum(parts) / len(parts) / 100.0, 2)
        return self._store(
            record.id,
            activity,
            status,
            planned,
            actual_type,
            planned_dur,
            actual_dur,
            intensity,
            structure,
            overall,
            analysis,
            commit=commit,
        )

    def mark_skipped(self, recommendation_id: int) -> Dict[str, Any]:
        record = self._ledger.get_recommendation(recommendation_id)
        if record is None:
            return {"status": "not_found"}
        row = RecommendationExecution(
            recommendation_id=recommendation_id,
            activity_id=None,
            execution_status="skipped",
            planned_type=record["recommended_workout_type"],
            actual_type=None,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return {"id": row.id, "execution_status": "skipped", "recommendation_id": recommendation_id}

    def _store(
        self,
        recommendation_id: Optional[int],
        activity: Activity,
        status: str,
        planned: Optional[str],
        actual: Optional[str],
        planned_dur: Optional[float] = None,
        actual_dur: Optional[float] = None,
        intensity: Optional[Dict[str, Any]] = None,
        structure: Optional[Dict[str, Any]] = None,
        overall: Optional[float] = None,
        analysis: Optional[Dict[str, Any]] = None,
        commit: bool = True,
    ) -> Dict[str, Any]:
        row = RecommendationExecution(
            recommendation_id=recommendation_id,
            activity_id=activity.activity_id,
            execution_status=status,
            planned_type=planned,
            actual_type=actual,
            planned_duration=planned_dur,
            actual_duration=actual_dur,
            intensity_adherence_json=intensity,
            structure_adherence_json=structure,
            overall_adherence=overall,
            analysis_json=analysis,
        )
        self.db.add(row)
        if commit:
            self.db.commit()
            self.db.refresh(row)
        else:
            self.db.flush()
        return {
            "id": row.id,
            "recommendation_id": recommendation_id,
            "activity_id": activity.activity_id,
            "execution_status": status,
            "planned_type": planned,
            "actual_type": actual,
            "planned_duration": planned_dur,
            "actual_duration": round(actual_dur, 1) if actual_dur is not None else None,
            "intensity_adherence": intensity,
            "structure_adherence": structure,
            "overall_adherence": overall,
            "note": "Adherence ≠ workout quality or physiological response.",
        }

    @staticmethod
    def _planned_duration_min(record: RecommendationRecord) -> Optional[float]:
        rx = record.workout_prescription_json or {}
        total = rx.get("total_duration_min")
        if isinstance(total, (int, float)):
            return float(total)
        return None

    @staticmethod
    def _duration_close(planned: Optional[float], actual: Optional[float]) -> bool:
        if planned is None or actual is None:
            return True
        return abs(planned - actual) <= max(10.0, planned * 0.2)
