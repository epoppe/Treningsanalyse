"""Faktisk treningskalender — ukedagsmal + dato-overstyring. Ingen Google Calendar."""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..config import get_settings
from ..database.models.coaching_v5 import TrainingAvailability
from .coaching_tx import finalize_write

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


class TrainingAvailabilityService:
    def __init__(self, db: Session):
        self.db = db

    def upsert(
        self,
        *,
        weekday: Optional[str] = None,
        on_date: Optional[date] = None,
        available: bool = True,
        max_duration_min: Optional[int] = None,
        preferred_session_types: Optional[List[str]] = None,
        avoid_hard: bool = False,
        allows_long_run: Optional[bool] = None,
        reason: Optional[str] = None,
        commit: bool = True,
    ) -> Dict[str, Any]:
        query = self.db.query(TrainingAvailability)
        if on_date is not None:
            row = query.filter(TrainingAvailability.date == on_date).first()
        elif weekday:
            row = query.filter(
                TrainingAvailability.weekday == weekday.lower(),
                TrainingAvailability.date.is_(None),
            ).first()
        else:
            raise ValueError("weekday or date required")
        if row is None:
            row = TrainingAvailability()
            self.db.add(row)
        row.weekday = weekday.lower() if weekday else (on_date.strftime("%A").lower() if on_date else None)
        row.date = on_date
        row.available = available
        row.max_duration_min = max_duration_min
        row.preferred_session_types_json = preferred_session_types
        row.avoid_hard = avoid_hard
        row.allows_long_run = allows_long_run
        row.reason = reason
        finalize_write(self.db, commit=commit)
        if commit:
            self.db.refresh(row)
        return self._to_dict(row)

    def constraints_for_week(self, week_start: date) -> List[Dict[str, Any]]:
        result = []
        for offset in range(7):
            day = week_start + timedelta(days=offset)
            result.append(self.constraint_for_date(day))
        return result

    def constraint_for_date(self, day: date) -> Dict[str, Any]:
        override = (
            self.db.query(TrainingAvailability)
            .filter(TrainingAvailability.date == day)
            .first()
        )
        if override:
            payload = self._to_dict(override)
            payload["source"] = "date_override"
            payload["date"] = day.isoformat()
            return payload
        weekday = day.strftime("%A").lower()
        template = (
            self.db.query(TrainingAvailability)
            .filter(TrainingAvailability.weekday == weekday, TrainingAvailability.date.is_(None))
            .first()
        )
        if template:
            payload = self._to_dict(template)
            payload["source"] = "weekday_template"
            payload["date"] = day.isoformat()
            return payload
        from_env = self._from_settings(weekday)
        if from_env:
            from_env["date"] = day.isoformat()
            from_env["source"] = "config"
            return from_env
        weekend = weekday in {"saturday", "sunday"}
        return {
            "date": day.isoformat(),
            "weekday": weekday,
            "available": True,
            "max_duration_min": 120 if weekend else 75,
            "preferred_session_types": [],
            "avoid_hard": False,
            "allows_long_run": weekend,
            "reason": None,
            "source": "default",
        }

    def _from_settings(self, weekday: str) -> Optional[Dict[str, Any]]:
        raw = getattr(get_settings(), "ATHLETE_AVAILABILITY_JSON", None)
        if not raw:
            return None
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            return None
        if isinstance(data, list):
            for item in data:
                if str(item.get("weekday", "")).lower() == weekday:
                    return {
                        "weekday": weekday,
                        "available": bool(item.get("available", True)),
                        "max_duration_min": item.get("max_duration_min"),
                        "preferred_session_types": item.get("preferred_session_types") or [],
                        "avoid_hard": bool(item.get("avoid_hard", False)),
                        "allows_long_run": item.get("allows_long_run"),
                        "reason": item.get("reason"),
                    }
        return None

    @staticmethod
    def _to_dict(row: TrainingAvailability) -> Dict[str, Any]:
        return {
            "id": row.id,
            "weekday": row.weekday,
            "date": row.date.isoformat() if row.date else None,
            "available": row.available,
            "max_duration_min": row.max_duration_min,
            "preferred_session_types": row.preferred_session_types_json or [],
            "avoid_hard": row.avoid_hard,
            "allows_long_run": row.allows_long_run,
            "reason": row.reason,
        }
