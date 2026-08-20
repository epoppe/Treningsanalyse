"""Coaching data integrity — set-based checks, consistent severity, no N+1."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database.models.activity import Activity
from ..database.models.coaching_v5 import (
    CoachingModelRegistryEntry,
    RecommendationExecution,
    RecommendationRecord,
    ShadowRecommendation,
    TrainingPlan,
    TrainingPlanVersion,
    ValidationRun,
)
from .builtin_model_registry import BuiltinModelRegistry
from .query_budget import assert_query_budget
from .status_semantics import IntegrityOverall, IntegritySeverity


class CoachingIntegrityService:
    def __init__(self, db: Session):
        self.db = db

    def check(self, *, max_queries: Optional[int] = None) -> Dict[str, Any]:
        if max_queries is not None:
            with assert_query_budget(self.db, max_queries=max_queries, label="integrity_check"):
                return self._check()
        return self._check()

    def _check(self) -> Dict[str, Any]:
        findings: List[Dict[str, Any]] = []

        bad_duration = (
            self.db.query(func.count(Activity.activity_id))
            .filter(Activity.duration.isnot(None), Activity.duration < 0)
            .scalar()
            or 0
        )
        if bad_duration:
            findings.append(self._finding("NEGATIVE_DURATION", IntegritySeverity.ERROR, bad_duration, False,
                                          "Activities with negative duration"))

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
            findings.append(self._finding("UNREALISTIC_HR", IntegritySeverity.WARNING, bad_hr, False,
                                          "Average HR outside 30–230 bpm"))

        orphan_exec = (
            self.db.query(func.count(RecommendationExecution.id))
            .filter(RecommendationExecution.recommendation_id.is_(None))
            .scalar()
            or 0
        )
        if orphan_exec:
            findings.append(self._finding("ORPHAN_EXECUTION", IntegritySeverity.ERROR, orphan_exec, False,
                                          "RecommendationExecution without recommendation_id"))

        # Plan versions without parent — set-based (no per-row parent lookup)
        plan_ids = {p.id for p in self.db.query(TrainingPlan.id).all()}
        if not plan_ids:
            orphan_versions = self.db.query(func.count(TrainingPlanVersion.id)).scalar() or 0
        else:
            orphan_versions = (
                self.db.query(func.count(TrainingPlanVersion.id))
                .filter(~TrainingPlanVersion.plan_id.in_(plan_ids))
                .scalar()
                or 0
            )
        if orphan_versions:
            findings.append(self._finding("PLAN_VERSION_WITHOUT_PARENT", IntegritySeverity.ERROR, orphan_versions, False,
                                          "TrainingPlanVersion references missing plan"))

        # Supersede graph — one load, in-memory traversal
        supersede_findings = self._supersede_graph_findings()
        findings.extend(supersede_findings)

        bad_shadow = (
            self.db.query(func.count(ShadowRecommendation.id))
            .filter(
                (ShadowRecommendation.model_key.is_(None))
                | (ShadowRecommendation.shadow_workout_type.is_(None))
            )
            .scalar()
            or 0
        )
        if bad_shadow:
            findings.append(self._finding("INVALID_SHADOW", IntegritySeverity.WARNING, bad_shadow, False,
                                          "Shadow recommendation missing model_key or workout type"))

        # ValidationRun vs registry / builtin — preload maps
        registry_pairs = {
            (r.model_key, r.version)
            for r in self.db.query(
                CoachingModelRegistryEntry.model_key, CoachingModelRegistryEntry.version
            ).all()
        }
        unknown = 0
        for run in self.db.query(ValidationRun.model_key, ValidationRun.model_version).all():
            if (run.model_key, run.model_version) in registry_pairs:
                continue
            if BuiltinModelRegistry.is_known(run.model_key, run.model_version):
                continue
            unknown += 1
        if unknown:
            findings.append(self._finding("VALIDATION_RUN_UNKNOWN_VERSION", IntegritySeverity.WARNING, unknown, False,
                                          "ValidationRun model/version not in registry or BuiltinModelRegistry"))

        status = self._overall(findings)
        return {"status": status, "findings": findings}

    def _supersede_graph_findings(self) -> List[Dict[str, Any]]:
        rows = self.db.query(
            RecommendationRecord.id,
            RecommendationRecord.superseded_by_id,
            RecommendationRecord.is_active,
            RecommendationRecord.as_of_date,
        ).all()
        by_id = {r.id: r for r in rows}
        ids = set(by_id)
        cycles = 0
        self_refs = 0
        missing_refs = 0
        active_but_superseded = 0
        for r in rows:
            if r.superseded_by_id is None:
                continue
            if r.superseded_by_id == r.id:
                self_refs += 1
                continue
            if r.superseded_by_id not in ids:
                missing_refs += 1
                continue
            # cycle detection — count each cycle once via min-id representative
            seen: Set[int] = set()
            cur = r.id
            while cur is not None:
                if cur in seen:
                    if min(seen) == r.id:
                        cycles += 1
                    break
                seen.add(cur)
                nxt = by_id.get(cur)
                cur = nxt.superseded_by_id if nxt else None
            if r.is_active and r.superseded_by_id is not None:
                active_but_superseded += 1

        # More than one active per as_of_date
        active_dates: Dict[Any, int] = {}
        for r in rows:
            if r.is_active and not r.superseded_by_id:
                active_dates[r.as_of_date] = active_dates.get(r.as_of_date, 0) + 1
        multi_active = sum(1 for n in active_dates.values() if n > 1)

        findings = []
        if self_refs:
            findings.append(self._finding("SUPERSEDE_SELF_REFERENCE", IntegritySeverity.CRITICAL, self_refs, False,
                                          "Recommendation superseded_by_id points to self"))
        if cycles:
            findings.append(self._finding("SUPERSEDE_CYCLE", IntegritySeverity.CRITICAL, cycles, False,
                                          "Cycle detected in supersede graph"))
        if missing_refs:
            findings.append(self._finding("SUPERSEDE_MISSING_TARGET", IntegritySeverity.ERROR, missing_refs, False,
                                          "superseded_by_id references missing record"))
        if active_but_superseded:
            findings.append(self._finding("ACTIVE_ALREADY_SUPERSEDED", IntegritySeverity.ERROR, active_but_superseded, False,
                                          "is_active=True but superseded_by_id is set"))
        if multi_active:
            findings.append(self._finding("MULTIPLE_ACTIVE_SAME_DATE", IntegritySeverity.WARNING, multi_active, False,
                                          "More than one active recommendation for same as_of_date"))
        return findings

    def repair_plan(self, *, dry_run: bool = True) -> Dict[str, Any]:
        report = self.check()
        actions = []
        for finding in report["findings"]:
            if finding.get("repairable"):
                actions.append(
                    {
                        "code": finding["code"],
                        "action": "manual_review_required",
                        "dry_run": dry_run,
                    }
                )
        return {
            "dry_run": dry_run,
            "actions": actions,
            "note": "Destructive repairs are never automatic.",
            "integrity": report,
        }

    @staticmethod
    def _finding(
        code: str,
        severity: IntegritySeverity,
        count: int,
        repairable: bool,
        description: str,
    ) -> Dict[str, Any]:
        return {
            "code": code,
            "severity": severity.value,
            "count": count,
            "repairable": repairable,
            "description": description,
        }

    @staticmethod
    def _overall(findings: List[Dict[str, Any]]) -> str:
        if not findings:
            return IntegrityOverall.HEALTHY.value
        severities = {f["severity"] for f in findings}
        if IntegritySeverity.CRITICAL.value in severities:
            return IntegrityOverall.CRITICAL.value
        if IntegritySeverity.ERROR.value in severities:
            return IntegrityOverall.ATTENTION_REQUIRED.value
        if IntegritySeverity.WARNING.value in severities:
            return IntegrityOverall.WARNINGS.value
        return IntegrityOverall.HEALTHY.value
