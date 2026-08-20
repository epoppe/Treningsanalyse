"""Session-RPE last vs objektive lastmål — avvik er evidens, ikke diagnose."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..database.models.activity import Activity
from ..database.models.coaching_v5 import AthleteFeedback
from .athlete_feedback_service import AthleteFeedbackService


class PerceivedLoadService:
    def __init__(self, db: Session):
        self.db = db
        self._feedback = AthleteFeedbackService(db)

    def analyze(self, activity: Activity) -> Dict[str, Any]:
        feedback = self._feedback.get_for_activity(activity.activity_id)
        duration_min = (float(activity.duration) / 60.0) if activity.duration else None
        rpe = feedback.get("rpe") if feedback else None
        srpe = round(duration_min * rpe, 1) if duration_min and rpe else None
        tss = activity.training_stress_score or activity.epoc
        te = activity.total_training_effect
        flags: List[str] = []
        expected_srpe = None
        if tss is not None and duration_min:
            expected_rpe = min(10.0, max(2.0, 2.5 + (float(tss) / max(duration_min, 1.0)) * 3.5))
            expected_srpe = round(duration_min * expected_rpe, 1)
        if srpe is not None and expected_srpe:
            if srpe > expected_srpe * 1.25:
                flags.append("higher_perceived_cost_than_expected")
            elif srpe < expected_srpe * 0.75:
                flags.append("lower_perceived_cost_than_expected")
        systematic = self._systematic_bias(activity.activity_id)
        return {
            "activity_id": activity.activity_id,
            "session_rpe_load": srpe,
            "rpe": rpe,
            "duration_min": round(duration_min, 1) if duration_min else None,
            "tss": float(tss) if tss is not None else None,
            "epoc": float(activity.epoc) if activity.epoc is not None else None,
            "training_effect": float(te) if te is not None else None,
            "expected_session_rpe_load": expected_srpe,
            "flags": flags,
            "systematic_bias": systematic,
            "feedback_missing": feedback is None,
            "note": "Single-session mismatch is not a diagnosis. Look for repeated bias.",
        }

    def _systematic_bias(self, current_id: str) -> Optional[str]:
        rows = (
            self.db.query(AthleteFeedback)
            .filter(AthleteFeedback.rpe.isnot(None))
            .order_by(AthleteFeedback.recorded_at.desc())
            .limit(8)
            .all()
        )
        if len(rows) < 4:
            return None
        high = 0
        for row in rows:
            activity = self.db.query(Activity).filter(Activity.activity_id == row.activity_id).first()
            if activity is None or not activity.duration or row.rpe is None:
                continue
            duration_min = float(activity.duration) / 60.0
            tss = activity.training_stress_score or activity.epoc
            if not tss:
                continue
            expected = min(10.0, max(2.0, 2.5 + float(tss) / max(duration_min, 1) * 3.5))
            if float(row.rpe) > expected * 1.2:
                high += 1
        if high >= 3:
            return "repeated_higher_rpe_than_objective_load"
        return None
