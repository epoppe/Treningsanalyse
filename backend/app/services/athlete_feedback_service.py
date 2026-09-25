"""Valgfri subjektiv tilbakemelding — ekstra evidens, ikke sannhet."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func

from sqlalchemy.orm import Session

from ..database.models.coaching_v5 import AthleteFeedback
from .coaching_tx import finalize_write

VALID_FEEL = {"very_easy", "easy", "as_expected", "hard", "very_hard"}
VALID_LEGS = {"fresh", "normal", "heavy"}
RPE_MIN, RPE_MAX = 1, 10
PAIN_MIN, PAIN_MAX = 0, 10
MOTIVATION_MIN, MOTIVATION_MAX = 1, 5
QUICK_FEEL = (
    {"value": "easy", "label": "Lettere enn forventet"},
    {"value": "as_expected", "label": "Som forventet"},
    {"value": "hard", "label": "Tyngre enn forventet"},
)


def feedback_scales() -> Dict[str, Any]:
    return {
        "rpe": {"min": RPE_MIN, "max": RPE_MAX},
        "pain": {"min": PAIN_MIN, "max": PAIN_MAX},
        "motivation": {"min": MOTIVATION_MIN, "max": MOTIVATION_MAX},
        "session_feel": sorted(VALID_FEEL),
        "legs": sorted(VALID_LEGS),
        "quick_feel": list(QUICK_FEEL),
    }


def feedback_on_or_before(recorded_at: Optional[datetime], cutoff: date) -> bool:
    """True when the row was recorded on cutoff or earlier. Missing time stays out."""
    if recorded_at is None:
        return False
    recorded_day = recorded_at.date() if isinstance(recorded_at, datetime) else recorded_at
    return recorded_day <= cutoff


def _in_range(name: str, value: Optional[int], low: int, high: int) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < low or value > high:
        raise ValueError(f"{name} must be an integer between {low} and {high}")


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
        commit: bool = True,
    ) -> Dict[str, Any]:
        self._validate(
            rpe=rpe,
            session_feel=session_feel,
            legs=legs,
            pain=pain,
            motivation=motivation,
        )
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
        finalize_write(self.db, commit=commit)
        if commit:
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

    def upsert(
        self,
        activity_id: str,
        *,
        rpe: Optional[int] = None,
        session_feel: Optional[str] = None,
        legs: Optional[str] = None,
        pain: Optional[int] = None,
        motivation: Optional[int] = None,
        notes: Optional[str] = None,
        commit: bool = True,
    ) -> Dict[str, Any]:
        """Replace the latest feedback for an activity.

        Ordinary edits do not insert another row and do not move recorded_at.
        The original timestamp is the moment the feedback became available.
        """
        self._validate(
            rpe=rpe,
            session_feel=session_feel,
            legs=legs,
            pain=pain,
            motivation=motivation,
        )
        row = (
            self.db.query(AthleteFeedback)
            .filter(AthleteFeedback.activity_id == str(activity_id))
            .order_by(AthleteFeedback.recorded_at.desc(), AthleteFeedback.id.desc())
            .first()
        )
        if row is None:
            return self.record(
                activity_id,
                rpe=rpe,
                session_feel=session_feel,
                legs=legs,
                pain=pain,
                motivation=motivation,
                notes=notes,
                commit=commit,
            )
        row.rpe = rpe
        row.session_feel = session_feel
        row.legs = legs
        row.pain = pain
        row.motivation = motivation
        row.notes = notes
        finalize_write(self.db, commit=commit)
        if commit:
            self.db.refresh(row)
        return self._to_dict(row)

    def recent(self, limit: int = 5) -> List[Dict[str, Any]]:
        rows = (
            self.db.query(AthleteFeedback)
            .order_by(AthleteFeedback.recorded_at.desc())
            .limit(limit)
            .all()
        )
        return [self._to_dict(r) for r in rows]

    def on_or_before(self, day: date, *, limit: int = 5) -> List[Dict[str, Any]]:
        """Latest feedback whose recorded day is on or before `day`."""
        rows = (
            self.db.query(AthleteFeedback)
            .filter(func.date(AthleteFeedback.recorded_at) <= day.isoformat())
            .order_by(AthleteFeedback.recorded_at.desc(), AthleteFeedback.id.desc())
            .limit(limit)
            .all()
        )
        return [self._to_dict(row) for row in rows]

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
            "provenance": "athlete_feedback",
            "ground_truth": False,
        }

    @staticmethod
    def _validate(
        *,
        rpe: Optional[int],
        session_feel: Optional[str],
        legs: Optional[str],
        pain: Optional[int],
        motivation: Optional[int],
    ) -> None:
        _in_range("rpe", rpe, RPE_MIN, RPE_MAX)
        _in_range("pain", pain, PAIN_MIN, PAIN_MAX)
        _in_range("motivation", motivation, MOTIVATION_MIN, MOTIVATION_MAX)
        if session_feel and session_feel not in VALID_FEEL:
            raise ValueError("invalid session_feel")
        if legs and legs not in VALID_LEGS:
            raise ValueError("invalid legs")
