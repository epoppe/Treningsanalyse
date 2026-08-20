"""Immutable recommendation ledger. Live advice may persist; backtest/preview must not."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..database.models.coaching_v5 import RecommendationRecord
from ..schemas.coaching import (
    AthleteStateSnapshotV1,
    DecisionStatus,
    DecisionTraceV1,
    ModelProvenanceV1,
    RecommendationSnapshotV1,
    WeeklyPlanSnapshotV1,
    WorkoutPrescriptionV1,
    coerce_enum,
    dump_validated,
    validate_snapshot,
)
from .coaching_provenance import build_provenance
from .coaching_tx import finalize_write
from .payload_hash import decision_payload_hash

# Same as_of + config + decision within this window → reuse existing record.
IDEMPOTENCY_WINDOW = timedelta(hours=6)


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
        commit: bool = True,
        is_shadow: bool = False,
        shadow_of_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        provenance = build_provenance(calibration=calibration)
        provenance = dump_validated(ModelProvenanceV1, provenance)
        decision_status = coerce_enum(
            DecisionStatus,
            recommendation.get("decision_status"),
            DecisionStatus.RECOMMEND,
        )
        decision_confidence = recommendation.get("decision_confidence")
        if decision_confidence is None:
            decision_confidence = recommendation.get("recommendation_confidence") or recommendation.get(
                "confidence"
            )
        evidence_strength = recommendation.get("evidence_strength")
        data_quality_score = None
        if isinstance(data_quality, dict):
            data_quality_score = data_quality.get("score")
        elif isinstance(data_quality, (int, float)):
            data_quality_score = float(data_quality)
        if data_quality_score is None:
            data_quality_score = recommendation.get("data_quality")
            if isinstance(data_quality_score, dict):
                data_quality_score = data_quality_score.get("score")

        d_hash = decision_payload_hash(
            workout_type=str(recommendation.get("workout_type") or "easy_run"),
            decision_status=decision_status.value if decision_status else None,
            evidence_strength=evidence_strength,
            decision_confidence=decision_confidence,
            prescription=recommendation.get("workout_prescription"),
            context_summary=recommendation.get("context_summary"),
        )
        if not persist:
            return {
                "persisted": False,
                "id": None,
                "provenance": provenance,
                "decision_payload_hash": d_hash,
                "note": "preview_or_backtest_not_recorded",
            }

        if not is_shadow:
            existing = self._find_idempotent(
                as_of_date=as_of_date,
                config_hash=provenance["config_hash"],
                decision_payload_hash=d_hash,
            )
            if existing is not None:
                payload = self._to_dict(existing)
                payload["idempotent_reuse"] = True
                return payload

        snapshot = dump_validated(
            RecommendationSnapshotV1,
            {
                "workout_type": str(recommendation.get("workout_type") or "easy_run"),
                "decision_status": decision_status.value if decision_status else None,
                "evidence_strength": evidence_strength,
                "decision_confidence": decision_confidence,
                "recommendation_confidence": decision_confidence,
                "data_quality": data_quality_score,
                "goal": recommendation.get("goal"),
                "training_phase": recommendation.get("training_phase"),
                "race_capability": recommendation.get("race_capability"),
                "context_summary": recommendation.get("context_summary"),
                "candidate_workouts": recommendation.get("candidate_workouts"),
                "workout_prescription": recommendation.get("workout_prescription"),
                "decision_trace": recommendation.get("decision_trace"),
                "safe_alternatives": recommendation.get("safe_alternatives"),
            },
        )
        row = RecommendationRecord(
            generated_at=datetime.now(timezone.utc),
            as_of_date=as_of_date,
            is_active=not is_shadow,
            model_version=provenance.get("engine") or "adaptive_coaching_v5",
            decision_engine_version=str(provenance.get("decision_engine_version") or "5"),
            calibration_version=str(provenance.get("calibration_version") or "2"),
            application_version=str(provenance.get("application_version") or "5.0.0"),
            ranker_version=provenance.get("ranker_version"),
            prescription_version=provenance.get("prescription_version"),
            config_hash=provenance["config_hash"],
            decision_payload_hash=d_hash,
            provenance_json=_json_safe(provenance),
            goal_snapshot_json=_json_safe(recommendation.get("goal")),
            athlete_state_snapshot_json=dump_validated(AthleteStateSnapshotV1, athlete_state or {}),
            input_context_json=_json_safe(
                {
                    "schema_version": 1,
                    "as_of_date": as_of_date.isoformat(),
                    "lookahead_bound": as_of_date.isoformat(),
                    "context_summary": recommendation.get("context_summary"),
                    "training_phase": recommendation.get("training_phase"),
                    "race_capability": recommendation.get("race_capability"),
                    "decision_engine": recommendation.get("decision_engine"),
                    "decision_status": decision_status.value if decision_status else None,
                    "evidence_strength": evidence_strength,
                    "decision_confidence": decision_confidence,
                    "data_quality": data_quality_score,
                }
            ),
            recommended_workout_type=snapshot.get("workout_type") or "easy_run",
            candidate_workouts_json=_json_safe(recommendation.get("candidate_workouts")),
            workout_prescription_json=dump_validated(
                WorkoutPrescriptionV1, recommendation.get("workout_prescription") or {}
            ),
            weekly_plan_json=dump_validated(
                WeeklyPlanSnapshotV1, weekly_plan or recommendation.get("weekly_plan") or {}
            ),
            evidence_strength=evidence_strength,
            recommendation_confidence=decision_confidence,
            decision_confidence=decision_confidence,
            data_quality_score=float(data_quality_score) if data_quality_score is not None else None,
            decision_status=decision_status.value if decision_status else None,
            decision_trace_json=validate_snapshot(
                DecisionTraceV1, recommendation.get("decision_trace") or []
            ),
            model_health=model_health,
            data_quality=_json_safe(data_quality if isinstance(data_quality, dict) else {"score": data_quality_score}),
            is_shadow=is_shadow,
            shadow_of_id=shadow_of_id,
        )
        self.db.add(row)
        finalize_write(self.db, commit=commit)
        if commit:
            self.db.refresh(row)
        else:
            self.db.flush()
        return self._to_dict(row)

    def get_recommendation(self, record_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.query(RecommendationRecord).filter(RecommendationRecord.id == record_id).first()
        return self._to_dict(row) if row else None

    def get_latest_active_recommendation(
        self,
        *,
        as_of_date: Optional[date] = None,
    ) -> Optional[Dict[str, Any]]:
        query = self.db.query(RecommendationRecord).filter(
            RecommendationRecord.is_active.is_(True),
            RecommendationRecord.is_shadow.is_(False),
        )
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
        commit: bool = True,
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
            commit=False,
        )
        if created.get("idempotent_reuse") and created.get("id") == record_id:
            finalize_write(self.db, commit=commit)
            return {
                "previous": self._to_dict(original),
                "current": created,
                "original_snapshot_unchanged": True,
                "idempotent_reuse": True,
            }
        # Only pointer fields change on the original row — snapshots stay immutable.
        original.superseded_by_id = created["id"]
        original.is_active = False
        finalize_write(self.db, commit=commit)
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

    def _find_idempotent(
        self,
        *,
        as_of_date: date,
        config_hash: str,
        decision_payload_hash: str,
    ) -> Optional[RecommendationRecord]:
        cutoff = datetime.now(timezone.utc) - IDEMPOTENCY_WINDOW
        return (
            self.db.query(RecommendationRecord)
            .filter(
                RecommendationRecord.as_of_date == as_of_date,
                RecommendationRecord.config_hash == config_hash,
                RecommendationRecord.decision_payload_hash == decision_payload_hash,
                RecommendationRecord.is_shadow.is_(False),
                RecommendationRecord.generated_at >= cutoff,
            )
            .order_by(RecommendationRecord.id.desc())
            .first()
        )

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
            "decision_payload_hash": row.decision_payload_hash,
            "provenance": validate_snapshot(ModelProvenanceV1, row.provenance_json),
            "goal_snapshot": row.goal_snapshot_json,
            "athlete_state_snapshot": validate_snapshot(
                AthleteStateSnapshotV1, row.athlete_state_snapshot_json
            ),
            "input_context": row.input_context_json,
            "recommended_workout_type": row.recommended_workout_type,
            "candidate_workouts": row.candidate_workouts_json,
            "workout_prescription": validate_snapshot(
                WorkoutPrescriptionV1, row.workout_prescription_json
            ),
            "weekly_plan": validate_snapshot(WeeklyPlanSnapshotV1, row.weekly_plan_json),
            "evidence_strength": row.evidence_strength,
            "recommendation_confidence": row.recommendation_confidence,
            "decision_confidence": row.decision_confidence
            if row.decision_confidence is not None
            else row.recommendation_confidence,
            "data_quality": row.data_quality_score,
            "decision_status": row.decision_status,
            "decision_trace": validate_snapshot(DecisionTraceV1, row.decision_trace_json),
            "model_health": row.model_health,
            "data_quality_detail": row.data_quality,
            "superseded_by_id": row.superseded_by_id,
            "is_shadow": bool(row.is_shadow),
            "shadow_of_id": row.shadow_of_id,
        }
