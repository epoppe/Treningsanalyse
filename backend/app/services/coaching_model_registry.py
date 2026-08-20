"""Model registry — experimental → shadow → eligible → active → retired."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..database.models.coaching_v5 import CoachingModelRegistryEntry
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
        gate: Dict[str, Any],
        commit: bool = True,
    ) -> Dict[str, Any]:
        """Promotion requires explicit gate evidence — never auto-activate."""
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
        # Retire previous active for same key
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
        row.promotion_gate_json = gate
        row.activated_at = datetime.now(timezone.utc)
        finalize_write(self.db, commit=commit)
        return self._to_dict(row)

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
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "activated_at": row.activated_at.isoformat() if row.activated_at else None,
            "notes": row.notes,
        }
