"""Aggregate coaching system health — no external monitoring platform."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database.models.coaching_v5 import (
    RecommendationExecution,
    RecommendationRecord,
    ShadowRecommendation,
    ValidationRun,
)
from ..database.models.sync_state import SyncState
from .coaching_model_registry import CoachingModelRegistry
from .freshness_policy import FreshnessPolicy
from .personalization_stability_service import PersonalizationStabilityService


class CoachingHealthService:
    def __init__(self, db: Session):
        self.db = db

    def report(self, day: Optional[date] = None) -> Dict[str, Any]:
        day = day or date.today()
        issues = []
        checks: Dict[str, Any] = {}

        sync = self.db.query(SyncState).order_by(SyncState.id.desc()).first()
        last_sync = None
        if sync is not None:
            last_sync = sync.last_synced_at or sync.updated_at
        checks["last_successful_garmin_sync"] = (
            last_sync.isoformat() if hasattr(last_sync, "isoformat") else last_sync
        )
        if last_sync is None:
            issues.append("no_sync_state")

        checks["db_migration_head"] = "alembic_head_runtime"

        active = CoachingModelRegistry(self.db).get_active("ranker")
        checks["active_coaching_model"] = active

        latest_run = (
            self.db.query(ValidationRun)
            .filter(ValidationRun.status == "completed")
            .order_by(ValidationRun.created_at.desc())
            .first()
        )
        checks["latest_validation_run_id"] = latest_run.id if latest_run else None
        checks["prospective_sample_count"] = self.db.query(RecommendationRecord).count()
        checks["execution_sample_count"] = self.db.query(RecommendationExecution).count()
        checks["shadow_sample_count"] = self.db.query(ShadowRecommendation).count()

        orphan_exec = (
            self.db.query(func.count(RecommendationExecution.id))
            .filter(RecommendationExecution.recommendation_id.is_(None))
            .scalar()
            or 0
        )
        checks["orphan_executions"] = orphan_exec
        if orphan_exec:
            issues.append("orphan_executions")

        stability = PersonalizationStabilityService(self.db).assess(as_of_date=day)
        checks["calibration_stability"] = stability.get("status")

        freshness = FreshnessPolicy.bundle(
            day,
            {"lt2": None, "hrv_baseline": None, "critical_speed": None},
        )
        checks["data_freshness"] = freshness

        if checks["prospective_sample_count"] < 5:
            issues.append("low_prospective_n")
        if latest_run is None:
            issues.append("no_validation_run")

        if not issues:
            status = "healthy"
        elif len(issues) == 1 and issues[0] in {"no_validation_run", "low_prospective_n", "no_sync_state"}:
            status = "degraded"
        else:
            status = "attention_required"

        return {
            "status": status,
            "checks": checks,
            "issues": issues,
            "as_of": day.isoformat(),
        }
