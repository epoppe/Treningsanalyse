"""Immutable validation runs — promotion evidence source of truth."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..database.models.coaching_v5 import ValidationRun
from .coaching_tx import finalize_write
from .payload_hash import payload_hash
from .temporal_model_validation_service import TemporalModelValidationService


VALIDATION_CODE_VERSION = "v7.0.0"


class ValidationRunService:
    def __init__(self, db: Session, storage=None):
        self.db = db
        self.storage = storage
        self._temporal = TemporalModelValidationService(db, storage)

    def create_walk_forward_run(
        self,
        *,
        model_key: str,
        model_version: str,
        start_date: date,
        end_date: date,
        min_train_days: int = 60,
        step_days: int = 30,
        config: Optional[Dict[str, Any]] = None,
        commit: bool = True,
    ) -> Dict[str, Any]:
        result = self._temporal.walk_forward(
            start_date=start_date,
            end_date=end_date,
            min_train_days=min_train_days,
            step_days=step_days,
        )
        fold_def = {
            "validation_type": "walk_forward",
            "min_train_days": min_train_days,
            "step_days": step_days,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }
        metrics = self._build_metrics(result)
        baseline_metrics = {
            "imitation_rate": result.get("aggregate", {}).get("baseline_metric"),
            "utility": result.get("aggregate", {}).get("baseline_utility"),
        }
        config = config or {}
        config_hash = payload_hash(config) if config else payload_hash(fold_def)
        sample_size = int(metrics.get("sample_size") or 0)
        bundle = {
            "config": config,
            "model_key": model_key,
            "model_version": model_version,
            "date_bounds": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "folds": result.get("folds"),
            "metric_definitions": {
                "imitation": "type compatibility with actual session",
                "short_term_utility": "observational post-session markers",
                "medium_term_utility": "14–21d TSB/CTL observational",
                "note": "Not causal; not counterfactual-as-truth",
            },
            "result": result.get("aggregate"),
            "validation_code_version": VALIDATION_CODE_VERSION,
        }
        row = ValidationRun(
            model_key=model_key,
            model_version=model_version,
            config_hash=config_hash,
            data_start=start_date,
            data_end=end_date,
            fold_definition_json=fold_def,
            metrics_json=metrics,
            baseline_metrics_json=baseline_metrics,
            sample_size=sample_size,
            validation_code_version=VALIDATION_CODE_VERSION,
            status="completed",
            reproducibility_bundle_json=bundle,
            result_fingerprint=self._fingerprint(bundle),
        )
        self.db.add(row)
        finalize_write(self.db, commit=commit)
        if commit:
            self.db.refresh(row)
        return self.to_dict(row)

    def get(self, run_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.query(ValidationRun).filter(ValidationRun.id == run_id).first()
        return self.to_dict(row) if row else None

    def export_reproducibility_bundle(self, run_id: int) -> Dict[str, Any]:
        row = self.db.query(ValidationRun).filter(ValidationRun.id == run_id).first()
        if row is None:
            raise ValueError("validation_run not found")
        if row.status != "completed":
            raise ValueError("only completed validation runs can be exported")
        return {
            "validation_run_id": row.id,
            "immutable": True,
            "bundle": row.reproducibility_bundle_json or {},
            "result_fingerprint": row.result_fingerprint,
            "validation_code_version": row.validation_code_version,
        }

    def prospective_dashboard_payload(self, run_id: Optional[int] = None) -> Dict[str, Any]:
        query = self.db.query(ValidationRun).filter(ValidationRun.status == "completed")
        if run_id:
            query = query.filter(ValidationRun.id == run_id)
        runs = query.order_by(ValidationRun.created_at.desc()).limit(20).all()
        return {
            "prospective_recommendations": sum(
                int((r.metrics_json or {}).get("coverage_n") or 0) for r in runs
            ),
            "prospective_outcomes": sum(
                int((r.metrics_json or {}).get("sample_size") or 0) for r in runs
            ),
            "shadow_comparisons": (runs[0].metrics_json or {}).get("shadow_comparisons") if runs else None,
            "promotion_candidates": [
                {"id": r.id, "model_key": r.model_key, "version": r.model_version, "delta": (r.metrics_json or {}).get("baseline_delta")}
                for r in runs
                if float((r.metrics_json or {}).get("baseline_delta") or 0) > 0
            ],
            "confidence_calibration": (runs[0].metrics_json or {}).get("confidence_calibration") if runs else None,
            "mesocycle_adherence": (runs[0].metrics_json or {}).get("mesocycle_adherence") if runs else None,
        }

    @staticmethod
    def _build_metrics(result: Dict[str, Any]) -> Dict[str, Any]:
        agg = result.get("aggregate") or {}
        folds = result.get("folds") or []
        by_type: Dict[str, Dict[str, Any]] = {}
        for fold in folds:
            wt = fold.get("model_recommendation") or "unknown"
            bucket = by_type.setdefault(wt, {"n": 0, "imitation_hits": 0, "utility_sum": 0.0, "utility_n": 0})
            bucket["n"] += 1
            if fold.get("imitation") is True:
                bucket["imitation_hits"] += 1
            util = (fold.get("utility") or {}).get("short_term_utility")
            if util is not None:
                bucket["utility_sum"] += float(util)
                bucket["utility_n"] += 1
        per_type = {}
        for k, v in by_type.items():
            per_type[k] = {
                "n": v["n"],
                "imitation_rate": round(v["imitation_hits"] / v["n"], 3) if v["n"] else None,
                "mean_short_term_utility": round(v["utility_sum"] / v["utility_n"], 3) if v["utility_n"] else None,
            }
        sample_size = int(agg.get("fold_count") or len(folds))
        return {
            "walk_forward": True,
            "fold_count": sample_size,
            "sample_size": sample_size,
            "imitation_rate": agg.get("model_metric"),
            "baseline_imitation_rate": agg.get("baseline_metric"),
            "baseline_delta": agg.get("delta"),
            "utility_metric": agg.get("model_utility"),
            "baseline_utility": agg.get("baseline_utility"),
            "utility_delta": agg.get("utility_delta"),
            "coverage": agg.get("coverage"),
            "abstention_rate": agg.get("abstention_rate"),
            "recovery_penalty": agg.get("recovery_penalty"),
            "by_session_type": per_type,
            "by_training_phase": agg.get("by_training_phase") or {},
            "confidence_calibration": agg.get("confidence_calibration"),
            "stability": agg.get("stability") or "watch",
            "guardrails_pass": bool(agg.get("guardrails_pass", True)),
            "calibration": agg.get("calibration"),
        }

    @staticmethod
    def _fingerprint(bundle: Dict[str, Any]) -> str:
        payload = json.dumps(bundle, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]

    @staticmethod
    def to_dict(row: ValidationRun) -> Dict[str, Any]:
        return {
            "id": row.id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "model_key": row.model_key,
            "model_version": row.model_version,
            "config_hash": row.config_hash,
            "data_start": row.data_start.isoformat() if row.data_start else None,
            "data_end": row.data_end.isoformat() if row.data_end else None,
            "fold_definition": row.fold_definition_json,
            "metrics": row.metrics_json,
            "baseline_metrics": row.baseline_metrics_json,
            "sample_size": row.sample_size,
            "validation_code_version": row.validation_code_version,
            "status": row.status,
            "result_fingerprint": row.result_fingerprint,
            "immutable": row.status == "completed",
        }
