"""Valgfri subjektiv tilbakemelding — ekstra evidens, ikke sannhet."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..database.models.coaching_v5 import AthleteFeedback

VALID_FEEL = {"very_easy", "easy", "as_expected", "hard", "very_hard"}
VALID_LEGS = {"fresh", "normal", "heavy"}


class AthleteFeedbackService:
    def __init__(self, db: Session):
        self.db = db

    def record(
        self,
        activity_id: str,
        *,
        rpe: Optional[int] = None,
        session_feel: Optional[str] = None,
        legs: Optional[str] = None,
        pain: Optional[int] = None,
        motivation: Optional[int] = None,
        notes: Optional[str] = None,
        recorded_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        if session_feel and session_feel not in VALID_FEEL:
            raise ValueError("invalid session_feel")
        if legs and legs not in VALID_LEGS:
            raise ValueError("invalid legs")
        row = AthleteFeedback(
            activity_id=str(activity_id),
            recorded_at=recorded_at or datetime.now(timezone.utc),
            rpe=rpe,
            session_feel=session_feel,
            legs=legs,
            pain=pain,
            motivation=motivation,
            notes=notes,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return self._to_dict(row)

    def get_for_activity(self, activity_id: str) -> Optional[Dict[str, Any]]:
        row = (
            self.db.query(AthleteFeedback)
            .filter(AthleteFeedback.activity_id == str(activity_id))
            .order_by(AthleteFeedback.recorded_at.desc())
            .first()
        )
        return self._to_dict(row) if row else None

    def recent(self, limit: int = 5) -> List[Dict[str, Any]]:
        rows = (
            self.db.query(AthleteFeedback)
            .order_by(AthleteFeedback.recorded_at.desc())
            .limit(limit)
            .all()
        )
        return [self._to_dict(r) for r in rows]

    @staticmethod
    def _to_dict(row: AthleteFeedback) -> Dict[str, Any]:
        return {
            "id": row.id,
            "activity_id": row.activity_id,
            "recorded_at": row.recorded_at.isoformat() if row.recorded_at else None,
            "rpe": row.rpe,
            "session_feel": row.session_feel,
            "legs": row.legs,
            "pain": row.pain,
            "motivation": row.motivation,
            "notes": row.notes,
            "optional": True,
        }
