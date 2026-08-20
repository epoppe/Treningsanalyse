"""Persistent ukeplaner med versjonering. Originalen overskrives aldri."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..database.models.coaching_v5 import TrainingPlan, TrainingPlanVersion


class TrainingPlanStore:
    def __init__(self, db: Session):
        self.db = db

    def persist_new_plan(
        self,
        *,
        week_start: date,
        payload: Dict[str, Any],
        previous_plan_id: Optional[int] = None,
        recommendation_id: Optional[int] = None,
        changes: Optional[List[Dict[str, Any]]] = None,
        reason: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        if previous_plan_id:
            prev = self.db.query(TrainingPlan).filter(TrainingPlan.id == previous_plan_id).first()
            if prev:
                prev.is_active = False
        plan = TrainingPlan(
            week_start=week_start,
            is_active=True,
            previous_plan_id=previous_plan_id,
            current_version_id=None,
        )
        self.db.add(plan)
        self.db.flush()
        version = TrainingPlanVersion(
            plan_id=plan.id,
            version=1,
            created_at=datetime.now(timezone.utc),
            previous_version_id=None,
            recommendation_id=recommendation_id,
            sessions_json=payload.get("sessions") or payload.get("days") or [],
            week_objective=payload.get("week_objective"),
            changes_json=changes,
            reason_json=reason,
            simulation_json=payload.get("simulation"),
            scores_json=payload.get("scores"),
        )
        self.db.add(version)
        self.db.flush()
        plan.current_version_id = version.id
        self.db.commit()
        self.db.refresh(plan)
        return self._to_dict(plan)

    def append_version(
        self,
        plan_id: int,
        *,
        sessions: List[Dict[str, Any]],
        week_objective: Optional[str] = None,
        changes: Optional[List[Dict[str, Any]]] = None,
        reason: Optional[List[str]] = None,
        simulation: Optional[Dict[str, Any]] = None,
        scores: Optional[Dict[str, Any]] = None,
        recommendation_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        plan = self.db.query(TrainingPlan).filter(TrainingPlan.id == plan_id).first()
        if plan is None:
            raise ValueError(f"plan {plan_id} not found")
        prev_version = plan.current_version
        next_no = (prev_version.version if prev_version else 0) + 1
        version = TrainingPlanVersion(
            plan_id=plan.id,
            version=next_no,
            created_at=datetime.now(timezone.utc),
            previous_version_id=prev_version.id if prev_version else None,
            recommendation_id=recommendation_id,
            sessions_json=sessions,
            week_objective=week_objective or (prev_version.week_objective if prev_version else None),
            changes_json=changes,
            reason_json=reason,
            simulation_json=simulation,
            scores_json=scores,
        )
        self.db.add(version)
        self.db.flush()
        plan.current_version_id = version.id
        plan.is_active = True
        self.db.commit()
        self.db.refresh(plan)
        return self._to_dict(plan)

    def get_active_plan(self, week_start: Optional[date] = None) -> Optional[Dict[str, Any]]:
        query = self.db.query(TrainingPlan).filter(TrainingPlan.is_active.is_(True))
        if week_start is not None:
            query = query.filter(TrainingPlan.week_start == week_start)
        plan = query.order_by(TrainingPlan.created_at.desc(), TrainingPlan.id.desc()).first()
        return self._to_dict(plan) if plan else None

    def get_plan(self, plan_id: int) -> Optional[Dict[str, Any]]:
        plan = self.db.query(TrainingPlan).filter(TrainingPlan.id == plan_id).first()
        return self._to_dict(plan) if plan else None

    @staticmethod
    def _to_dict(plan: TrainingPlan) -> Dict[str, Any]:
        version = plan.current_version
        return {
            "plan_id": plan.id,
            "previous_plan_id": plan.previous_plan_id,
            "week_start": plan.week_start.isoformat() if plan.week_start else None,
            "is_active": plan.is_active,
            "version": version.version if version else None,
            "version_id": version.id if version else None,
            "previous_version_id": version.previous_version_id if version else None,
            "created_at": version.created_at.isoformat() if version and version.created_at else None,
            "sessions": version.sessions_json if version else [],
            "week_objective": version.week_objective if version else None,
            "changes": version.changes_json if version else None,
            "reason": version.reason_json if version else None,
            "simulation": version.simulation_json if version else None,
            "scores": version.scores_json if version else None,
        }
