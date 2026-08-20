"""Kontrollerte coaching-eksperimenter. Starter aldri uten eksplisitt brukerønske."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..database.models.coaching_v5 import TrainingExperiment


class TrainingExperimentService:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        *,
        hypothesis: str,
        start_date: date,
        end_date: Optional[date] = None,
        intervention: Optional[Dict[str, Any]] = None,
        baseline: Optional[Dict[str, Any]] = None,
        metric_outcomes: Optional[List[str]] = None,
        stop_conditions: Optional[Dict[str, Any]] = None,
        user_confirmed: bool = False,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        row = TrainingExperiment(
            hypothesis=hypothesis,
            start_date=start_date,
            end_date=end_date,
            intervention_json=intervention,
            baseline_json=baseline,
            metric_outcomes_json=metric_outcomes,
            stop_conditions_json=stop_conditions,
            status="draft",
            user_confirmed=False,
            notes=notes,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        if user_confirmed:
            return self.start(row.id, user_confirmed=True)
        return self._to_dict(row)

    def start(self, experiment_id: int, *, user_confirmed: bool) -> Dict[str, Any]:
        if not user_confirmed:
            raise PermissionError("Experiments never start without explicit user confirmation.")
        row = self.db.query(TrainingExperiment).filter(TrainingExperiment.id == experiment_id).first()
        if row is None:
            raise ValueError("experiment not found")
        row.user_confirmed = True
        row.status = "active"
        self.db.commit()
        self.db.refresh(row)
        return self._to_dict(row)

    def stop(self, experiment_id: int, *, reason: Optional[str] = None) -> Dict[str, Any]:
        row = self.db.query(TrainingExperiment).filter(TrainingExperiment.id == experiment_id).first()
        if row is None:
            raise ValueError("experiment not found")
        row.status = "stopped"
        if reason:
            row.notes = ((row.notes or "") + f"\nstop: {reason}").strip()
        self.db.commit()
        self.db.refresh(row)
        return self._to_dict(row)

    def get_active(self) -> Optional[Dict[str, Any]]:
        row = (
            self.db.query(TrainingExperiment)
            .filter(TrainingExperiment.status == "active", TrainingExperiment.user_confirmed.is_(True))
            .order_by(TrainingExperiment.created_at.desc())
            .first()
        )
        return self._to_dict(row) if row else None

    @staticmethod
    def _to_dict(row: TrainingExperiment) -> Dict[str, Any]:
        return {
            "id": row.id,
            "hypothesis": row.hypothesis,
            "start_date": row.start_date.isoformat() if row.start_date else None,
            "end_date": row.end_date.isoformat() if row.end_date else None,
            "intervention": row.intervention_json,
            "baseline": row.baseline_json,
            "metric_outcomes": row.metric_outcomes_json,
            "stop_conditions": row.stop_conditions_json,
            "status": row.status,
            "user_confirmed": row.user_confirmed,
            "notes": row.notes,
        }
