"""Export/restore coaching history Garmin cannot reconstruct."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..database.models.coaching_v5 import (
    AthleteFeedback,
    CalibrationSnapshot,
    RecommendationExecution,
    RecommendationRecord,
    ShadowRecommendation,
    TrainingAvailability,
    TrainingExperiment,
    TrainingPlan,
    TrainingPlanVersion,
)
from ..schemas.coaching import RecommendationSnapshotV1, validate_snapshot


class CoachingDataExportService:
    MANIFEST_VERSION = 1

    def __init__(self, db: Session):
        self.db = db

    def export_manifest(self) -> Dict[str, Any]:
        recommendations = [self._rec(r) for r in self.db.query(RecommendationRecord).all()]
        plans = []
        for plan in self.db.query(TrainingPlan).all():
            versions = (
                self.db.query(TrainingPlanVersion)
                .filter(TrainingPlanVersion.plan_id == plan.id)
                .order_by(TrainingPlanVersion.version.asc())
                .all()
            )
            plans.append(
                {
                    "plan_id": plan.id,
                    "week_start": plan.week_start.isoformat() if plan.week_start else None,
                    "is_active": plan.is_active,
                    "previous_plan_id": plan.previous_plan_id,
                    "versions": [
                        {
                            "version": v.version,
                            "content_hash": v.content_hash,
                            "sessions": v.sessions_json,
                            "week_objective": v.week_objective,
                            "changes": v.changes_json,
                            "reason": v.reason_json,
                        }
                        for v in versions
                    ],
                }
            )
        payload = {
            "manifest_version": self.MANIFEST_VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "contains_credentials": False,
            "recommendations": recommendations,
            "plans": plans,
            "feedback": [
                {
                    "activity_id": f.activity_id,
                    "rpe": f.rpe,
                    "session_feel": f.session_feel,
                    "legs": f.legs,
                    "pain": f.pain,
                    "motivation": f.motivation,
                    "notes": f.notes,
                    "recorded_at": f.recorded_at.isoformat() if f.recorded_at else None,
                }
                for f in self.db.query(AthleteFeedback).all()
            ],
            "executions": [
                {
                    "recommendation_id": e.recommendation_id,
                    "activity_id": e.activity_id,
                    "execution_status": e.execution_status,
                    "planned_type": e.planned_type,
                    "actual_type": e.actual_type,
                    "overall_adherence": e.overall_adherence,
                }
                for e in self.db.query(RecommendationExecution).all()
            ],
            "calibration_snapshots": [
                {
                    "parameter": c.parameter,
                    "effective_value": c.effective_value_json,
                    "sample_count": c.sample_count,
                    "confidence": c.confidence,
                    "as_of_date": c.as_of_date.isoformat() if c.as_of_date else None,
                }
                for c in self.db.query(CalibrationSnapshot).all()
            ],
            "availability": [
                {
                    "weekday": a.weekday,
                    "date": a.date.isoformat() if a.date else None,
                    "available": a.available,
                    "max_duration_min": a.max_duration_min,
                    "avoid_hard": a.avoid_hard,
                    "reason": a.reason,
                }
                for a in self.db.query(TrainingAvailability).all()
            ],
            "experiments": [
                {
                    "hypothesis": x.hypothesis,
                    "start_date": x.start_date.isoformat() if x.start_date else None,
                    "end_date": x.end_date.isoformat() if x.end_date else None,
                    "status": x.status,
                    "user_confirmed": x.user_confirmed,
                }
                for x in self.db.query(TrainingExperiment).all()
            ],
            "shadow_recommendations": [
                {
                    "as_of_date": s.as_of_date.isoformat() if s.as_of_date else None,
                    "production": s.production_workout_type,
                    "shadow": s.shadow_workout_type,
                    "model_key": s.model_key,
                    "model_version": s.model_version,
                }
                for s in self.db.query(ShadowRecommendation).all()
            ],
        }
        return payload

    def export_json(self) -> str:
        return json.dumps(self.export_manifest(), indent=2, default=str)

    def validate_restore_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        errors: List[str] = []
        if not isinstance(payload, dict):
            return {"valid": False, "errors": ["payload_not_object"]}
        if payload.get("contains_credentials"):
            errors.append("credentials_not_allowed")
        if int(payload.get("manifest_version") or 0) < 1:
            errors.append("missing_manifest_version")
        for rec in payload.get("recommendations") or []:
            checked = validate_snapshot(RecommendationSnapshotV1, {
                "workout_type": rec.get("recommended_workout_type") or "easy_run",
                **(rec.get("workout_prescription") or {}),
            })
            if checked.get("degraded") and not rec.get("recommended_workout_type"):
                errors.append("recommendation_missing_workout_type")
        return {
            "valid": not errors,
            "errors": errors,
            "counts": {
                "recommendations": len(payload.get("recommendations") or []),
                "plans": len(payload.get("plans") or []),
                "feedback": len(payload.get("feedback") or []),
            },
        }

    @staticmethod
    def _rec(row: RecommendationRecord) -> Dict[str, Any]:
        return {
            "id": row.id,
            "as_of_date": row.as_of_date.isoformat() if row.as_of_date else None,
            "recommended_workout_type": row.recommended_workout_type,
            "config_hash": row.config_hash,
            "decision_payload_hash": row.decision_payload_hash,
            "decision_status": row.decision_status,
            "evidence_strength": row.evidence_strength,
            "decision_confidence": row.decision_confidence,
            "data_quality": row.data_quality_score,
            "model_version": row.model_version,
            "provenance": row.provenance_json,
            "workout_prescription": row.workout_prescription_json,
            "is_active": row.is_active,
            "superseded_by_id": row.superseded_by_id,
        }
