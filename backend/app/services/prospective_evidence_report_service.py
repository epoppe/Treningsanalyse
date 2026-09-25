"""Canonical prospective evidence report — recorded recommendations only."""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from statistics import mean
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..database.models.coaching_v5 import (
    CalibrationSnapshot,
    RecommendationRecord,
    ShadowRecommendation,
)
from .canonical_prospective_observation import CanonicalProspectiveObservationService
from .outcome_maturity import is_usable_status
from .personalization_evidence_policy import PersonalizationLevel
from .plan_stability import PlanStabilityService
from .recommendation_utility_evaluator import RecommendationUtilityEvaluator
from .sample_sufficiency_policy import SampleSufficiencyPolicy


def _section(sample_count: int, **payload: Any) -> Dict[str, Any]:
    return {"sample_count": sample_count, **payload}


class ProspectiveEvidenceReportService:
    """
    Operational report: is the coaching system improving under real use?

    Uses canonical prospective observations — never reconstructed backtests,
    and never one recommendation row per superseded snapshot.
    """

    def __init__(self, db: Session):
        self.db = db
        self._utility = RecommendationUtilityEvaluator(db)
        self._sufficiency = SampleSufficiencyPolicy()
        self._canonical = CanonicalProspectiveObservationService(db)

    def report(
        self,
        *,
        start: Optional[date] = None,
        end: Optional[date] = None,
        window_days: int = 90,
    ) -> Dict[str, Any]:
        end = end or date.today()
        start = start or (end - timedelta(days=window_days))
        observations = self._canonical.resolve(start=start, end=end, today=end)
        raw_rows = (
            self.db.query(RecommendationRecord)
            .filter(
                RecommendationRecord.as_of_date >= start,
                RecommendationRecord.as_of_date <= end,
            )
            .all()
        )
        shadow_rows = [row for row in raw_rows if row.is_shadow]
        production_rows = [row for row in raw_rows if not row.is_shadow]
        superseded_rows = max(0, len(production_rows) - len(observations))

        status_counts = Counter()
        type_counts = Counter()
        executed = modified = skipped = unplanned = replaced = pending_execution = 0
        adherence_vals: List[float] = []
        adherence_dates: List[date] = []
        short_vals: List[float] = []
        short_dates: List[date] = []
        short_weights: List[float] = []
        medium_vals: List[float] = []
        medium_dates: List[date] = []
        recovery_vals: List[float] = []
        recovery_dates: List[date] = []
        recovery_weights: List[float] = []
        expected_vals: List[float] = []
        feedback_n = 0
        pending_short = pending_medium = 0
        personalization = Counter()
        explicit_matches = legacy_matches = 0

        for observation in observations:
            obs_date = date.fromisoformat(observation["as_of_date"])
            status_counts[observation.get("decision_status") or "unknown"] += 1
            type_counts[observation.get("recommended_workout_type") or "unknown"] += 1
            execution_status = (observation.get("execution_status") or "").lower()
            if execution_status == "pending":
                pending_execution += 1
            elif execution_status in {"completed", "executed", "done", "followed"}:
                executed += 1
            elif execution_status in {"modified", "partial"}:
                modified += 1
            elif execution_status in {"skipped", "missed"}:
                skipped += 1
            elif execution_status == "replaced":
                replaced += 1
            elif execution_status == "unplanned":
                unplanned += 1
            if observation.get("match_source") == "explicit_execution":
                explicit_matches += 1
            elif observation.get("match_source") == "legacy_heuristic":
                legacy_matches += 1

            if observation.get("overall_adherence") is not None and execution_status != "pending":
                adherence_vals.append(float(observation["overall_adherence"]))
                adherence_dates.append(obs_date)

            utility = self._utility.evaluate(
                recommended_type=observation.get("recommended_workout_type"),
                actual_type=observation.get("actual_type"),
                as_of=obs_date,
                decision_confidence=observation.get("decision_confidence"),
                actual_load=observation.get("actual_load"),
                today=end,
            )
            weight = float(observation.get("evidence_weight") or 0.0)
            if utility.get("short_term_maturity") == "pending":
                pending_short += 1
            elif is_usable_status(utility.get("short_term_maturity")) and utility.get("short_term_utility") is not None:
                short_vals.append(float(utility["short_term_utility"]))
                short_dates.append(obs_date)
                short_weights.append(weight or 1.0)
            if utility.get("medium_term_maturity") == "pending":
                pending_medium += 1
            elif is_usable_status(utility.get("medium_term_maturity")) and utility.get("medium_term_utility") is not None:
                medium_vals.append(float(utility["medium_term_utility"]))
                medium_dates.append(obs_date)
            observed = utility.get("observed_recovery_response") or {}
            if is_usable_status(observed.get("maturity_status")) and observed.get("value") is not None:
                recovery_vals.append(float(observed["value"]))
                recovery_dates.append(obs_date)
                recovery_weights.append(weight or 1.0)
            expected = utility.get("expected_recovery_cost") or {}
            if expected.get("value") is not None:
                expected_vals.append(float(expected["value"]))
            if observation.get("subjective_feedback"):
                feedback_n += 1

            level = (observation.get("provenance_json") or {}).get("personalization_level")
            personalization[str(level) if level else PersonalizationLevel.DEFAULT] += 1

        shadows = (
            self.db.query(ShadowRecommendation)
            .filter(ShadowRecommendation.as_of_date >= start, ShadowRecommendation.as_of_date <= end)
            .all()
        )
        agree = sum(1 for row in shadows if row.production_workout_type == row.shadow_workout_type)
        shadow_n = len(shadows)

        plan = PlanStabilityService().from_history(self.db, as_of=end, window_days=(end - start).days or 1)
        versions_n = plan.get("versions_in_window") or 0
        cal_n = self.db.query(CalibrationSnapshot).count()
        dq_scores = [row.data_quality_score for row in production_rows if row.data_quality_score is not None]
        canonical_dates = [date.fromisoformat(row["as_of_date"]) for row in observations]

        short_sufficiency = self._sufficiency.assess_weighted(
            domain="workout_effectiveness",
            observation_dates=short_dates,
            evidence_weights=short_weights,
            as_of=end,
            data_quality=mean(dq_scores) if dq_scores else None,
        )
        recovery_sufficiency = self._sufficiency.assess_weighted(
            domain="recovery_cost",
            observation_dates=recovery_dates,
            evidence_weights=recovery_weights,
            as_of=end,
        )
        execution_dates = [
            date.fromisoformat(row["as_of_date"])
            for row in observations
            if row.get("execution_status") != "pending"
        ]
        execution_weights = [
            float(row.get("evidence_weight") or 0.0)
            for row in observations
            if row.get("execution_status") != "pending"
        ]
        execution_sufficiency = self._sufficiency.assess_weighted(
            domain="execution_patterns",
            observation_dates=execution_dates,
            evidence_weights=execution_weights,
            as_of=end,
        )

        return {
            "period": {"start": start.isoformat(), "end": end.isoformat()},
            "sample_counts": {
                "recommendation_rows": len(production_rows),
                "canonical_observations": len(observations),
                "excluded_superseded_or_duplicate": superseded_rows,
                "excluded_shadow_rows": len(shadow_rows),
                "execution_outcomes": executed + modified + skipped + replaced + unplanned,
                "pending_execution": pending_execution,
                "adherence_scores": len(adherence_vals),
                "short_term_recovery_outcomes": len(short_vals),
                "pending_short_term": pending_short,
                "medium_term_outcomes": len(medium_vals),
                "pending_medium_term": pending_medium,
                "observed_recovery_responses": len(recovery_vals),
                "subjective_feedback_observations": feedback_n,
                "explicit_execution_matches": explicit_matches,
                "legacy_heuristic_matches": legacy_matches,
            },
            "recommendations": _section(
                len(observations),
                count=len(observations),
                raw_row_count=len(production_rows),
                executed=executed,
                modified=modified,
                replaced=replaced,
                skipped=skipped,
                unplanned=unplanned,
                pending=pending_execution,
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
                pending_count=pending_execution,
                sufficiency=execution_sufficiency,
                note="Adherence/feasibility is not physiological effectiveness.",
            ),
            "outcomes": _section(
                len(short_vals),
                evaluated=len(short_vals),
                pending_count=pending_short,
                short_term_utility=round(mean(short_vals), 3) if short_vals else None,
                short_term_sample_count=len(short_vals),
                short_term_sufficiency=short_sufficiency,
                medium_term_utility=round(mean(medium_vals), 3) if medium_vals else None,
                medium_term_sample_count=len(medium_vals),
                pending_medium_term=pending_medium,
                observed_recovery_response=round(mean(recovery_vals), 3) if recovery_vals else None,
                observed_recovery_sample_count=len(recovery_vals),
                observed_recovery_sufficiency=recovery_sufficiency,
                expected_recovery_cost=round(mean(expected_vals), 3) if expected_vals else None,
                expected_recovery_sample_count=len(expected_vals),
                # Alias: observed response only, never the expected envelope.
                recovery_cost=round(mean(recovery_vals), 3) if recovery_vals else None,
                subjective_feedback_sample_count=feedback_n,
            ),
            "confidence_calibration": _section(
                len(short_vals),
                pairs=len(short_vals),
                note=(
                    "Binary target lives in DecisionConfidenceMonitor: "
                    "favorable_outcome iff mature short_term_utility >= 0.55. "
                    "Do not treat this section as a calibration score."
                ),
            ),
            "production_vs_shadow": _section(
                shadow_n,
                agreement_rate=round(agree / shadow_n, 3) if shadow_n else None,
                disagreement=shadow_n - agree,
                excluded_from_production_evidence=True,
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
            "evidence_sufficiency": short_sufficiency,
            "canonical_observation_dates": [day.isoformat() for day in canonical_dates],
            "note": (
                "Recorded prospective evidence only, one observation per decision chain. "
                "Pending windows are excluded from metric denominators. "
                "No conclusion stronger than SampleSufficiencyPolicy allows. "
                "Not a causal claim."
            ),
        }
