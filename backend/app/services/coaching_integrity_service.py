"""Coaching data integrity — detect issues; do not auto-repair destructively."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database.models.activity import Activity
from ..database.models.coaching_v5 import (
    RecommendationExecution,
    RecommendationRecord,
    ShadowRecommendation,
    TrainingPlan,
    TrainingPlanVersion,
    ValidationRun,
)
from .coaching_model_registry import CoachingModelRegistry


class CoachingIntegrityService:
    def __init__(self, db: Session):
        self.db = db

    def check(self) -> Dict[str, Any]:
        findings: List[Dict[str, Any]] = []

        # Duplicate activity ids impossible with PK — check duplicate start_time+duration heuristic
        # Impossible timestamps / negative durations / unrealistic HR
        bad_duration = (
            self.db.query(func.count(Activity.activity_id))
            .filter(Activity.duration.isnot(None), Activity.duration < 0)
            .scalar()
            or 0
        )
        if bad_duration:
            findings.append({"code": "negative_duration", "count": bad_duration, "severity": False})

        bad_hr = (
            self.db.query(func.count(Activity.activity_id))
            .filter(
                Activity.average_heart_rate.isnot(None),
                ((Activity.average_heart_rate < 30) | (Activity.average_heart_rate > 230)),
            )
            .scalar()
            or 0
        )
        if bad_hr:
            findings.append({"code": "unrealistic_hr", "count": bad_hr, "severity": False})

        orphan_exec = (
            self.db.query(RecommendationExecution)
            .filter(RecommendationExecution.recommendation_id.is_(None))
            .count()
        )
        if orphan_exec:
            findings.append({"code": "orphan_execution", "count": orphan_exec, "severity": True})

        # Plan versions without parent
        orphan_versions = 0
        for ver in self.db.query(TrainingPlanVersion).all():
            parent = self.db.query(TrainingPlan).filter(TrainingPlan.id == ver.plan_id).first()
            if parent is None:
                orphan_versions += 1
        if orphan_versions:
            findings.append({"code": "plan_version_without_parent", "count": orphan_versions, "severity": False})

        # Supersede cycles (simple detection)
        cycles = 0
        for rec in self.db.query(RecommendationRecord).filter(RecommendationRecord.superseded_by_id.isnot(None)).all():
            seen = {rec.id}
            cur = rec.superseded_by_id
            steps = 0
            while cur is not None and steps < 20:
                if cur in seen:
                    cycles += 1
                    break
                seen.add(cur)
                nxt = self.db.query(RecommendationRecord).filter(RecommendationRecord.id == cur).first()
                cur = nxt.superseded_by_id if nxt else None
                steps += 1
        if cycles:
            findings.append({"code": "supersede_cycle", "count": cycles, "severity": False})

        # Shadow without model key
        bad_shadow = (
            self.db.query(ShadowRecommendation)
            .filter(
                (ShadowRecommendation.model_key.is_(None))
                | (ShadowRecommendation.shadow_workout_type.is_(None))
            )
            .count()
        )
        if bad_shadow:
            findings.append({"code": "invalid_shadow", "count": bad_shadow, "severity": True})

        # ValidationRun referencing unknown registry version (warn only)
        unknown_versions = 0
        for run in self.db.query(ValidationRun).limit(100).all():
            reg = CoachingModelRegistry(self.db).list_models(run.model_key)
            if reg and not any(r.get("version") == run.model_version for r in reg):
                # Builtin default allowed
                if run.model_version not in {"default", "v7", "v7.0.0", "exp-1"}:
                    unknown_versions += 1
        if unknown_versions:
            findings.append({"code": "validation_run_unknown_version", "count": unknown_versions, "severity": False})

        status = "ok" if not findings else ("repairable" if all(f.get("repairable") for f in findings) else "attention")
        return {"status": status, "findings": findings}

    def repair_plan(self, *, dry_run: bool = True) -> Dict[str, Any]:
        """Only non-destructive repairs: clear orphan execution recommendation links stay; mark notes."""
        report = self.check()
        actions = []
        for finding in report["findings"]:
            if finding["code"] == "orphan_execution" and finding.get("repairable"):
                actions.append(
                    {
                        "action": "leave_orphan_execution",
                        "reason": "Manual review required — not auto-deleted",
                        "dry_run": dry_run,
                    }
                )
            if finding["code"] == "invalid_shadow" and finding.get("repairable"):
                actions.append(
                    {
                        "action": "leave_invalid_shadow",
                        "reason": "Manual review required — not auto-deleted",
                        "dry_run": dry_run,
                    }
                )
        return {
            "dry_run": dry_run,
            "actions": actions,
            "note": "Destructive repairs are never automatic.",
            "integrity": report,
        }
