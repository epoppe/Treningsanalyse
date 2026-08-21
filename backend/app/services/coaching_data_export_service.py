"""Export/restore coaching history Garmin cannot reconstruct."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..database.models.coaching_v5 import (
    AthleteFeedback,
    CalibrationSnapshot,
    CoachingModelRegistryEntry,
    RecommendationExecution,
    RecommendationRecord,
    ShadowRecommendation,
    TrainingAvailability,
    TrainingExperiment,
    TrainingPlan,
    TrainingPlanVersion,
    ValidationRun,
)
from ..schemas.coaching import RecommendationSnapshotV1, validate_snapshot
from .coaching_integrity_service import CoachingIntegrityService


class CoachingDataExportService:
    MANIFEST_VERSION = 2

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
                            "created_at": v.created_at.isoformat() if v.created_at else None,
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
                    "linked_at": e.linked_at.isoformat() if e.linked_at else None,
                }
                for e in self.db.query(RecommendationExecution).all()
            ],
            "calibration_snapshots": [
                {
                    "parameter": c.parameter,
                    "effective_value": c.effective_value_json,
                    "default_value": c.default_value_json,
                    "personalized_value": c.personalized_value_json,
                    "use_personalized": c.use_personalized,
                    "sample_count": c.sample_count,
                    "confidence": c.confidence,
                    "as_of_date": c.as_of_date.isoformat() if c.as_of_date else None,
                    "method": c.method,
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
                    "intervention": x.intervention_json,
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
                    "config_hash": s.config_hash,
                    "payload": s.payload_json,
                }
                for s in self.db.query(ShadowRecommendation).all()
            ],
            "validation_runs": [
                {
                    "model_key": v.model_key,
                    "model_version": v.model_version,
                    "config_hash": v.config_hash,
                    "data_start": v.data_start.isoformat() if v.data_start else None,
                    "data_end": v.data_end.isoformat() if v.data_end else None,
                    "sample_size": v.sample_size,
                    "validation_code_version": v.validation_code_version,
                    "status": v.status,
                    "metrics": v.metrics_json,
                    "baseline_metrics": v.baseline_metrics_json,
                }
                for v in self.db.query(ValidationRun).all()
            ],
            "model_registry": [
                {
                    "model_key": m.model_key,
                    "version": m.version,
                    "status": m.status,
                    "config": m.config_json,
                    "promotion_gate": m.promotion_gate_json,
                    "notes": m.notes,
                    "activated_at": m.activated_at.isoformat() if m.activated_at else None,
                }
                for m in self.db.query(CoachingModelRegistryEntry).all()
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
            checked = validate_snapshot(
                RecommendationSnapshotV1,
                {
                    "workout_type": rec.get("recommended_workout_type") or "easy_run",
                    **(rec.get("workout_prescription") or {}),
                },
            )
            if checked.get("degraded") and not rec.get("recommended_workout_type"):
                errors.append("recommendation_missing_workout_type")
        return {
            "valid": not errors,
            "errors": errors,
            "counts": {
                "recommendations": len(payload.get("recommendations") or []),
                "plans": len(payload.get("plans") or []),
                "feedback": len(payload.get("feedback") or []),
                "executions": len(payload.get("executions") or []),
                "validation_runs": len(payload.get("validation_runs") or []),
                "model_registry": len(payload.get("model_registry") or []),
            },
        }

    def restore(
        self,
        payload: Dict[str, Any],
        *,
        run_integrity: bool = True,
        commit: bool = True,
    ) -> Dict[str, Any]:
        """Restore coaching ledger. Never restores credentials. Returns RestoreValidationReport."""
        validation = self.validate_restore_payload(payload)
        if not validation.get("valid"):
            return {
                "ok": False,
                "errors": validation.get("errors") or ["invalid_payload"],
                "restored_counts": {},
                "integrity": None,
                "note": "Restore aborted — payload failed validation.",
            }

        id_map: Dict[int, int] = {}
        restored: Dict[str, int] = {
            "recommendations": 0,
            "plans": 0,
            "plan_versions": 0,
            "executions": 0,
            "feedback": 0,
            "calibration_snapshots": 0,
            "availability": 0,
            "experiments": 0,
            "shadow_recommendations": 0,
            "validation_runs": 0,
            "model_registry": 0,
        }

        for rec in payload.get("recommendations") or []:
            old_id = rec.get("id")
            row = RecommendationRecord(
                as_of_date=self._parse_date(rec.get("as_of_date")) or date.today(),
                is_active=bool(rec.get("is_active", False)),
                model_version=rec.get("model_version") or "default",
                decision_engine_version=rec.get("decision_engine_version") or "restored",
                calibration_version=rec.get("calibration_version") or "restored",
                application_version=rec.get("application_version") or "restored",
                config_hash=rec.get("config_hash") or "restored",
                decision_payload_hash=rec.get("decision_payload_hash"),
                recommended_workout_type=rec.get("recommended_workout_type") or "easy_run",
                workout_prescription_json=rec.get("workout_prescription"),
                evidence_strength=rec.get("evidence_strength"),
                decision_confidence=rec.get("decision_confidence"),
                data_quality_score=rec.get("data_quality"),
                decision_status=rec.get("decision_status"),
                provenance_json=rec.get("provenance"),
                superseded_by_id=None,
            )
            self.db.add(row)
            self.db.flush()
            if old_id is not None:
                id_map[int(old_id)] = row.id
            restored["recommendations"] += 1

        for rec in payload.get("recommendations") or []:
            old_id = rec.get("id")
            old_super = rec.get("superseded_by_id")
            if old_id is None or old_super is None:
                continue
            new_id = id_map.get(int(old_id))
            new_super = id_map.get(int(old_super))
            if new_id and new_super:
                row = self.db.get(RecommendationRecord, new_id)
                if row:
                    row.superseded_by_id = new_super

        for plan_payload in payload.get("plans") or []:
            plan = TrainingPlan(
                week_start=self._parse_date(plan_payload.get("week_start")) or date.today(),
                is_active=bool(plan_payload.get("is_active", True)),
            )
            self.db.add(plan)
            self.db.flush()
            restored["plans"] += 1
            for v in plan_payload.get("versions") or []:
                self.db.add(
                    TrainingPlanVersion(
                        plan_id=plan.id,
                        version=int(v.get("version") or 1),
                        sessions_json=v.get("sessions"),
                        week_objective=v.get("week_objective"),
                        changes_json=v.get("changes"),
                        reason_json=v.get("reason"),
                        content_hash=v.get("content_hash"),
                    )
                )
                restored["plan_versions"] += 1

        for fb in payload.get("feedback") or []:
            if not fb.get("activity_id"):
                continue
            self.db.add(
                AthleteFeedback(
                    activity_id=str(fb["activity_id"]),
                    rpe=fb.get("rpe"),
                    session_feel=fb.get("session_feel"),
                    legs=fb.get("legs"),
                    pain=fb.get("pain"),
                    motivation=fb.get("motivation"),
                    notes=fb.get("notes"),
                )
            )
            restored["feedback"] += 1

        for ex in payload.get("executions") or []:
            old_rec = ex.get("recommendation_id")
            new_rec = id_map.get(int(old_rec)) if old_rec is not None else None
            self.db.add(
                RecommendationExecution(
                    recommendation_id=new_rec,
                    activity_id=ex.get("activity_id"),
                    execution_status=ex.get("execution_status") or "unknown",
                    planned_type=ex.get("planned_type"),
                    actual_type=ex.get("actual_type"),
                    overall_adherence=ex.get("overall_adherence"),
                )
            )
            restored["executions"] += 1

        for c in payload.get("calibration_snapshots") or []:
            self.db.add(
                CalibrationSnapshot(
                    parameter=c.get("parameter") or "unknown",
                    effective_value_json=c.get("effective_value"),
                    default_value_json=c.get("default_value"),
                    personalized_value_json=c.get("personalized_value"),
                    use_personalized=bool(c.get("use_personalized", False)),
                    sample_count=int(c.get("sample_count") or 0),
                    confidence=c.get("confidence"),
                    as_of_date=self._parse_date(c.get("as_of_date")),
                    method=c.get("method"),
                )
            )
            restored["calibration_snapshots"] += 1

        for a in payload.get("availability") or []:
            self.db.add(
                TrainingAvailability(
                    weekday=a.get("weekday"),
                    date=self._parse_date(a.get("date")),
                    available=bool(a.get("available", True)),
                    max_duration_min=a.get("max_duration_min"),
                    avoid_hard=bool(a.get("avoid_hard", False)),
                    reason=a.get("reason"),
                )
            )
            restored["availability"] += 1

        for x in payload.get("experiments") or []:
            start = self._parse_date(x.get("start_date"))
            if not start or not x.get("hypothesis"):
                continue
            self.db.add(
                TrainingExperiment(
                    hypothesis=x["hypothesis"],
                    start_date=start,
                    end_date=self._parse_date(x.get("end_date")),
                    status=x.get("status") or "draft",
                    user_confirmed=bool(x.get("user_confirmed", False)),
                    intervention_json=x.get("intervention"),
                )
            )
            restored["experiments"] += 1

        for s in payload.get("shadow_recommendations") or []:
            as_of = self._parse_date(s.get("as_of_date"))
            if not as_of or not s.get("shadow"):
                continue
            self.db.add(
                ShadowRecommendation(
                    as_of_date=as_of,
                    model_key=s.get("model_key") or "shadow",
                    model_version=s.get("model_version") or "unknown",
                    production_workout_type=s.get("production"),
                    shadow_workout_type=s["shadow"],
                    config_hash=s.get("config_hash"),
                    payload_json=s.get("payload"),
                )
            )
            restored["shadow_recommendations"] += 1

        for v in payload.get("validation_runs") or []:
            ds = self._parse_date(v.get("data_start"))
            de = self._parse_date(v.get("data_end"))
            if not ds or not de:
                continue
            self.db.add(
                ValidationRun(
                    model_key=v.get("model_key") or "ranker",
                    model_version=v.get("model_version") or "unknown",
                    config_hash=v.get("config_hash") or "restored",
                    data_start=ds,
                    data_end=de,
                    sample_size=int(v.get("sample_size") or 0),
                    validation_code_version=v.get("validation_code_version") or "restored",
                    status=v.get("status") or "completed",
                    metrics_json=v.get("metrics"),
                    baseline_metrics_json=v.get("baseline_metrics"),
                )
            )
            restored["validation_runs"] += 1

        for m in payload.get("model_registry") or []:
            self.db.add(
                CoachingModelRegistryEntry(
                    model_key=m.get("model_key") or "ranker",
                    version=m.get("version") or "unknown",
                    status=m.get("status") or "experimental",
                    config_json=m.get("config"),
                    promotion_gate_json=m.get("promotion_gate"),
                    notes=m.get("notes"),
                )
            )
            restored["model_registry"] += 1

        if commit:
            self.db.commit()
        else:
            self.db.flush()

        integrity = CoachingIntegrityService(self.db).check() if run_integrity else None
        return {
            "ok": True,
            "errors": [],
            "restored_counts": restored,
            "integrity": integrity,
            "contains_credentials": False,
            "note": "RestoreValidationReport — secrets/tokens never restored.",
        }

    @staticmethod
    def _parse_date(value: Any) -> Optional[date]:
        if value is None:
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
        except ValueError:
            return None

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
            "decision_engine_version": row.decision_engine_version,
            "calibration_version": row.calibration_version,
            "application_version": row.application_version,
            "provenance": row.provenance_json,
            "workout_prescription": row.workout_prescription_json,
            "is_active": row.is_active,
            "superseded_by_id": row.superseded_by_id,
        }
