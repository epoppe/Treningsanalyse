"""Model registry — promotion requires immutable ValidationRun evidence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..database.models.coaching_v5 import CoachingModelRegistryEntry, ValidationRun
from ..schemas.coaching import ModelRegistryStatus, coerce_enum
from .coaching_tx import finalize_write


class CoachingModelRegistry:
    def __init__(self, db: Session):
        self.db = db

    def register(
        self,
        *,
        model_key: str,
        version: str,
        config: Optional[Dict[str, Any]] = None,
        status: str = ModelRegistryStatus.EXPERIMENTAL.value,
        notes: Optional[str] = None,
        commit: bool = True,
    ) -> Dict[str, Any]:
        existing = (
            self.db.query(CoachingModelRegistryEntry)
            .filter(
                CoachingModelRegistryEntry.model_key == model_key,
                CoachingModelRegistryEntry.version == version,
            )
            .first()
        )
        if existing:
            return {**self._to_dict(existing), "idempotent_reuse": True}
        status_e = coerce_enum(ModelRegistryStatus, status, ModelRegistryStatus.EXPERIMENTAL)
        row = CoachingModelRegistryEntry(
            model_key=model_key,
            version=version,
            status=status_e.value,
            config_json=config,
            notes=notes,
        )
        self.db.add(row)
        finalize_write(self.db, commit=commit)
        if commit:
            self.db.refresh(row)
        return self._to_dict(row)

    def promote(
        self,
        *,
        model_key: str,
        version: str,
        validation_run_id: Optional[int] = None,
        gate: Optional[Dict[str, Any]] = None,
        manual_override: bool = False,
        override_reason: Optional[str] = None,
        commit: bool = True,
    ) -> Dict[str, Any]:
        """
        Promotion derives evidence from immutable ValidationRun.

        Caller-supplied `gate` is rejected unless manual_override=True with reason
        (legacy / emergency only).
        """
        if validation_run_id is None and not manual_override:
            raise ValueError("promotion requires validation_run_id (or manual_override=true)")

        derived_gate: Dict[str, Any]
        if validation_run_id is not None:
            run = self.db.query(ValidationRun).filter(ValidationRun.id == validation_run_id).first()
            if run is None:
                raise ValueError("validation_run not found")
            if run.status != "completed":
                raise ValueError("promotion blocked: validation_run is not completed/immutable")
            if run.model_key != model_key:
                raise ValueError("validation_run model_key mismatch")
            derived_gate = self._gate_from_validation_run(run)
            derived_gate["validation_run_id"] = run.id
        elif manual_override:
            if not override_reason:
                raise ValueError("manual_override requires override_reason")
            if not gate:
                raise ValueError("manual_override requires gate dict")
            derived_gate = dict(gate)
            derived_gate["manual_override"] = True
            derived_gate["override_reason"] = override_reason
        else:
            raise ValueError("promotion requires validation_run_id")

        self._assert_gate(derived_gate)

        row = (
            self.db.query(CoachingModelRegistryEntry)
            .filter(
                CoachingModelRegistryEntry.model_key == model_key,
                CoachingModelRegistryEntry.version == version,
            )
            .first()
        )
        if row is None:
            raise ValueError("model version not registered")

        actives = (
            self.db.query(CoachingModelRegistryEntry)
            .filter(
                CoachingModelRegistryEntry.model_key == model_key,
                CoachingModelRegistryEntry.status == ModelRegistryStatus.ACTIVE.value,
            )
            .all()
        )
        for active in actives:
            active.status = ModelRegistryStatus.RETIRED.value
        row.status = ModelRegistryStatus.ACTIVE.value
        row.promotion_gate_json = derived_gate
        row.validation_run_id = validation_run_id
        row.activated_at = datetime.now(timezone.utc)
        if manual_override:
            notes = (row.notes or "") + f"\n[override] {override_reason}"
            row.notes = notes.strip()
        finalize_write(self.db, commit=commit)
        return self._to_dict(row)

    @staticmethod
    def _gate_from_validation_run(run: ValidationRun) -> Dict[str, Any]:
        metrics = run.metrics_json or {}
        baseline_delta = metrics.get("utility_delta")
        if baseline_delta is None:
            baseline_delta = metrics.get("baseline_delta")
        return {
            "walk_forward": bool(metrics.get("walk_forward", True)),
            "baseline_delta": baseline_delta,
            "sample_size": int(metrics.get("sample_size") or run.sample_size or 0),
            "stability": metrics.get("stability") or "watch",
            "guardrails_pass": bool(metrics.get("guardrails_pass", False)),
            "calibration": metrics.get("calibration") or metrics.get("confidence_calibration"),
            "utility_metric": metrics.get("utility_metric"),
            "imitation_rate": metrics.get("imitation_rate"),
            "source": "validation_run",
        }

    @staticmethod
    def _assert_gate(gate: Dict[str, Any]) -> None:
        required = ("walk_forward", "baseline_delta", "sample_size", "stability", "guardrails_pass")
        missing = [k for k in required if k not in gate]
        if missing:
            raise ValueError(f"promotion gate incomplete: missing {missing}")
        if not gate.get("guardrails_pass"):
            raise ValueError("promotion blocked: guardrails_pass is false")
        if float(gate.get("baseline_delta") or 0) <= 0:
            raise ValueError("promotion blocked: model does not beat baseline out-of-sample")
        if int(gate.get("sample_size") or 0) < 20:
            raise ValueError("promotion blocked: insufficient sample_size")
        if gate.get("stability") not in {"stable", "watch"}:
            raise ValueError("promotion blocked: unstable personalization/model")

    def set_status(
        self,
        *,
        model_key: str,
        version: str,
        status: str,
        commit: bool = True,
    ) -> Dict[str, Any]:
        row = (
            self.db.query(CoachingModelRegistryEntry)
            .filter(
                CoachingModelRegistryEntry.model_key == model_key,
                CoachingModelRegistryEntry.version == version,
            )
            .first()
        )
        if row is None:
            raise ValueError("model version not registered")
        status_e = coerce_enum(ModelRegistryStatus, status, ModelRegistryStatus.EXPERIMENTAL)
        if status_e == ModelRegistryStatus.ACTIVE:
            raise ValueError("use promote() to activate a model")
        row.status = status_e.value
        finalize_write(self.db, commit=commit)
        return self._to_dict(row)

    def get_active(self, model_key: str) -> Optional[Dict[str, Any]]:
        row = (
            self.db.query(CoachingModelRegistryEntry)
            .filter(
                CoachingModelRegistryEntry.model_key == model_key,
                CoachingModelRegistryEntry.status == ModelRegistryStatus.ACTIVE.value,
            )
            .order_by(CoachingModelRegistryEntry.activated_at.desc())
            .first()
        )
        return self._to_dict(row) if row else {
            "model_key": model_key,
            "version": "default",
            "status": ModelRegistryStatus.ACTIVE.value,
            "note": "builtin_default",
        }

    def list_models(self, model_key: Optional[str] = None) -> List[Dict[str, Any]]:
        query = self.db.query(CoachingModelRegistryEntry)
        if model_key:
            query = query.filter(CoachingModelRegistryEntry.model_key == model_key)
        return [self._to_dict(r) for r in query.order_by(CoachingModelRegistryEntry.created_at.desc()).all()]

    @staticmethod
    def _to_dict(row: CoachingModelRegistryEntry) -> Dict[str, Any]:
        return {
            "id": row.id,
            "model_key": row.model_key,
            "version": row.version,
            "status": row.status,
            "config": row.config_json,
            "promotion_gate": row.promotion_gate_json,
            "validation_run_id": getattr(row, "validation_run_id", None),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "activated_at": row.activated_at.isoformat() if row.activated_at else None,
            "notes": row.notes,
        }
