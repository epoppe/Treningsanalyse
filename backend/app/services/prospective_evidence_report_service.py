"""Canonical prospective evidence report — recorded recommendations only."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from statistics import mean
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..database.models.coaching_v5 import (
    CalibrationSnapshot,
    RecommendationExecution,
    RecommendationRecord,
    ShadowRecommendation,
    TrainingPlanVersion,
)
from .personalization_evidence_policy import PersonalizationLevel
from .plan_stability import PlanStabilityService
from .recommendation_utility_evaluator import RecommendationUtilityEvaluator
from .sample_sufficiency_policy import SampleSufficiencyPolicy


def _section(sample_count: int, **payload: Any) -> Dict[str, Any]:
    return {"sample_count": sample_count, **payload}


class ProspectiveEvidenceReportService:
    """
    Operational report: is the coaching system improving under real use?

    Uses RECORDED prospective recommendations only — never reconstructed backtests.
    """

    def __init__(self, db: Session):
        self.db = db
        self._utility = RecommendationUtilityEvaluator(db)
        self._sufficiency = SampleSufficiencyPolicy()

    def report(
        self,
        *,
        start: Optional[date] = None,
        end: Optional[date] = None,
        window_days: int = 90,
    ) -> Dict[str, Any]:
        end = end or date.today()
        start = start or (end - timedelta(days=window_days))

        recs = (
            self.db.query(RecommendationRecord)
            .filter(
                RecommendationRecord.as_of_date >= start,
                RecommendationRecord.as_of_date <= end,
                RecommendationRecord.is_shadow.is_(False),
            )
            .all()
        )
        # Prefer latest active-or-superseded chain tip per day for counts of "decisions"
        by_day: Dict[date, List[RecommendationRecord]] = defaultdict(list)
        for r in recs:
            by_day[r.as_of_date].append(r)

        execs = (
            self.db.query(RecommendationExecution)
            .filter(RecommendationExecution.recommendation_id.isnot(None))
            .all()
        )
        exec_by_rec = {e.recommendation_id: e for e in execs if e.recommendation_id}

        status_counts = Counter()
        type_counts = Counter()
        executed = modified = skipped = unplanned = 0
        adherence_vals: List[float] = []
        utilities: List[Dict[str, Any]] = []
        conf_pairs: List[tuple] = []
        personalization = Counter()

        for r in recs:
            status_counts[r.decision_status or "unknown"] += 1
            type_counts[r.recommended_workout_type or "unknown"] += 1
            ex = exec_by_rec.get(r.id)
            if ex is None:
                continue
            status = (ex.execution_status or "").lower()
            if status in {"completed", "executed", "done"}:
                executed += 1
            elif status in {"modified", "partial"}:
                modified += 1
            elif status in {"skipped", "missed"}:
                skipped += 1
            elif status in {"unplanned"}:
                unplanned += 1
            else:
                executed += 1 if ex.activity_id else skipped
            if ex.overall_adherence is not None:
                adherence_vals.append(float(ex.overall_adherence))
            util = self._utility.evaluate(
                recommended_type=r.recommended_workout_type,
                actual_type=ex.actual_type,
                as_of=r.as_of_date,
                decision_confidence=r.decision_confidence,
            )
            utilities.append(util)
            if r.decision_confidence is not None and util.get("short_term_utility") is not None:
                conf_pairs.append((float(r.decision_confidence), float(util["short_term_utility"])))

            # Personalization level from provenance / sample proxies
            level = ((r.provenance_json or {}) if isinstance(r.provenance_json, dict) else {}).get(
                "personalization_level"
            )
            if level:
                personalization[str(level)] += 1
            else:
                personalization[PersonalizationLevel.DEFAULT] += 1

        short = [u["short_term_utility"] for u in utilities if u.get("short_term_utility") is not None]
        medium = [u["medium_term_utility"] for u in utilities if u.get("medium_term_utility") is not None]
        recovery = [u["recovery_cost"] for u in utilities if u.get("recovery_cost") is not None]

        shadows = (
            self.db.query(ShadowRecommendation)
            .filter(ShadowRecommendation.as_of_date >= start, ShadowRecommendation.as_of_date <= end)
            .all()
        )
        agree = sum(1 for s in shadows if s.production_workout_type == s.shadow_workout_type)
        shadow_n = len(shadows)

        plan = PlanStabilityService().from_history(self.db, as_of=end, window_days=(end - start).days or 1)
        versions_n = plan.get("versions_in_window") or 0

        cal_n = self.db.query(CalibrationSnapshot).count()
        dq_scores = [r.data_quality_score for r in recs if r.data_quality_score is not None]

        sufficiency = self._sufficiency.assess(
            domain="workout_effectiveness",
            sample_count=len(utilities),
            observation_dates=[r.as_of_date for r in recs],
            as_of=end,
            data_quality=mean(dq_scores) if dq_scores else None,
        )

        return {
            "period": {"start": start.isoformat(), "end": end.isoformat()},
            "recommendations": _section(
                len(recs),
                count=len(recs),
                executed=executed,
                modified=modified,
                skipped=skipped,
                unplanned=unplanned,
                by_type=dict(type_counts),
            ),
            "decision_status": _section(
                sum(status_counts.values()),
                recommend=status_counts.get("recommend", 0),
                weak_preference=status_counts.get("weak_preference", 0),
                abstain=status_counts.get("abstain", 0) + status_counts.get("insufficient_data", 0),
                other=dict(status_counts),
            ),
            "execution": _section(
                len(adherence_vals),
                adherence=round(mean(adherence_vals), 3) if adherence_vals else None,
                execution_quality=round(mean(adherence_vals), 3) if adherence_vals else None,
            ),
            "outcomes": _section(
                len(utilities),
                evaluated=len(utilities),
                short_term_utility=round(mean(short), 3) if short else None,
                medium_term_utility=round(mean(medium), 3) if medium else None,
                recovery_cost=round(mean(recovery), 3) if recovery else None,
            ),
            "confidence_calibration": _section(
                len(conf_pairs),
                pairs=len(conf_pairs),
                note="Use DecisionConfidenceMonitor for binned calibration — do not overclaim here.",
            ),
            "production_vs_shadow": _section(
                shadow_n,
                agreement_rate=round(agree / shadow_n, 3) if shadow_n else None,
                disagreement=shadow_n - agree,
            ),
            "plan": _section(
                versions_n,
                replans=versions_n,
                material_replans=plan.get("material_changes") or 0,
                plan_stability=plan.get("status"),
            ),
            "personalization": _section(
                sum(personalization.values()),
                default=personalization.get(PersonalizationLevel.DEFAULT, 0),
                emerging_personal=personalization.get(PersonalizationLevel.EMERGING_PERSONAL, 0),
                personal_supported=personalization.get(PersonalizationLevel.PERSONAL_SUPPORTED, 0),
                personal_strong=personalization.get(PersonalizationLevel.PERSONAL_STRONG, 0),
            ),
            "data_quality": _section(
                len(dq_scores),
                mean_score=round(mean(dq_scores), 3) if dq_scores else None,
                calibration_snapshots=cal_n,
            ),
            "evidence_sufficiency": sufficiency,
            "note": (
                "Recorded prospective evidence only. "
                "No conclusion stronger than SampleSufficiencyPolicy allows. "
                "Not a causal claim."
            ),
        }
