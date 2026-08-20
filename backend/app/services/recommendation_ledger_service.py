"""Immutable recommendation ledger. Live advice may persist; backtest/preview must not."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..database.models.coaching_v5 import RecommendationRecord
from .coaching_provenance import build_provenance


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


class RecommendationLedgerService:
    def __init__(self, db: Session):
        self.db = db

    def record_recommendation(
        self,
        recommendation: Dict[str, Any],
        *,
        as_of_date: date,
        persist: bool = True,
        athlete_state: Optional[Dict[str, Any]] = None,
        weekly_plan: Optional[Dict[str, Any]] = None,
        model_health: Optional[str] = None,
        calibration: Optional[Dict[str, Any]] = None,
        data_quality: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        provenance = build_provenance(calibration=calibration)
        if not persist:
            return {
                "persisted": False,
                "id": None,
                "provenance": provenance,
                "note": "preview_or_backtest_not_recorded",
            }

        row = RecommendationRecord(
            generated_at=datetime.now(timezone.utc),
            as_of_date=as_of_date,
            is_active=True,
            model_version=provenance["engine"],
            decision_engine_version=provenance["decision_engine_version"],
            calibration_version=provenance["calibration_version"],
            application_version=provenance["application_version"],
            ranker_version=provenance.get("ranker_version"),
            prescription_version=provenance.get("prescription_version"),
            config_hash=provenance["config_hash"],
            provenance_json=_json_safe(provenance),
            goal_snapshot_json=_json_safe(recommendation.get("goal")),
            athlete_state_snapshot_json=_json_safe(athlete_state),
            input_context_json=_json_safe(
                {
                    "as_of_date": as_of_date.isoformat(),
                    "lookahead_bound": as_of_date.isoformat(),
                    "context_summary": recommendation.get("context_summary"),
                    "training_phase": recommendation.get("training_phase"),
                    "race_capability": recommendation.get("race_capability"),
                    "decision_engine": recommendation.get("decision_engine"),
                    "decision_status": recommendation.get("decision_status"),
                    "evidence_strength": recommendation.get("evidence_strength"),
                }
            ),
            recommended_workout_type=str(recommendation.get("workout_type") or "easy_run"),
            candidate_workouts_json=_json_safe(recommendation.get("candidate_workouts")),
            workout_prescription_json=_json_safe(recommendation.get("workout_prescription")),
            weekly_plan_json=_json_safe(weekly_plan or recommendation.get("weekly_plan")),
            evidence_strength=recommendation.get("evidence_strength"),
            recommendation_confidence=recommendation.get("recommendation_confidence")
            or recommendation.get("confidence"),
            decision_status=recommendation.get("decision_status"),
            decision_trace_json=_json_safe(recommendation.get("decision_trace")),
            model_health=model_health,
            data_quality=_json_safe(data_quality),
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return self._to_dict(row)

    def get_recommendation(self, record_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.query(RecommendationRecord).filter(RecommendationRecord.id == record_id).first()
        return self._to_dict(row) if row else None

    def get_latest_active_recommendation(
        self,
        *,
        as_of_date: Optional[date] = None,
    ) -> Optional[Dict[str, Any]]:
        query = self.db.query(RecommendationRecord).filter(RecommendationRecord.is_active.is_(True))
        if as_of_date is not None:
            query = query.filter(RecommendationRecord.as_of_date == as_of_date)
        row = query.order_by(RecommendationRecord.generated_at.desc(), RecommendationRecord.id.desc()).first()
        return self._to_dict(row) if row else None

    def supersede_recommendation(
        self,
        record_id: int,
        new_recommendation: Dict[str, Any],
        *,
        as_of_date: date,
        athlete_state: Optional[Dict[str, Any]] = None,
        weekly_plan: Optional[Dict[str, Any]] = None,
        model_health: Optional[str] = None,
        calibration: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        original = self.db.query(RecommendationRecord).filter(RecommendationRecord.id == record_id).first()
        if original is None:
            raise ValueError(f"recommendation {record_id} not found")
        original_snapshot = {
            "recommended_workout_type": original.recommended_workout_type,
            "input_context_json": original.input_context_json,
            "config_hash": original.config_hash,
        }
        created = self.record_recommendation(
            new_recommendation,
            as_of_date=as_of_date,
            persist=True,
            athlete_state=athlete_state,
            weekly_plan=weekly_plan,
            model_health=model_health,
            calibration=calibration,
        )
        # Only pointer fields change on the original row — snapshots stay immutable.
        original.superseded_by_id = created["id"]
        original.is_active = False
        self.db.commit()
        reloaded = self.get_recommendation(record_id)
        return {
            "previous": reloaded,
            "current": created,
            "original_snapshot_unchanged": (
                reloaded
                and reloaded["recommended_workout_type"] == original_snapshot["recommended_workout_type"]
                and reloaded["config_hash"] == original_snapshot["config_hash"]
            ),
        }

    @staticmethod
    def _to_dict(row: RecommendationRecord) -> Dict[str, Any]:
        return {
            "id": row.id,
            "persisted": True,
            "generated_at": row.generated_at.isoformat() if row.generated_at else None,
            "as_of_date": row.as_of_date.isoformat() if row.as_of_date else None,
            "is_active": row.is_active,
            "model_version": row.model_version,
            "decision_engine_version": row.decision_engine_version,
            "calibration_version": row.calibration_version,
            "application_version": row.application_version,
            "ranker_version": row.ranker_version,
            "prescription_version": row.prescription_version,
            "config_hash": row.config_hash,
            "provenance": row.provenance_json,
            "goal_snapshot": row.goal_snapshot_json,
            "athlete_state_snapshot": row.athlete_state_snapshot_json,
            "input_context": row.input_context_json,
            "recommended_workout_type": row.recommended_workout_type,
            "candidate_workouts": row.candidate_workouts_json,
            "workout_prescription": row.workout_prescription_json,
            "weekly_plan": row.weekly_plan_json,
            "evidence_strength": row.evidence_strength,
            "recommendation_confidence": row.recommendation_confidence,
            "decision_status": row.decision_status,
            "decision_trace": row.decision_trace_json,
            "model_health": row.model_health,
            "data_quality": row.data_quality,
            "superseded_by_id": row.superseded_by_id,
        }
