"""Aggreger recorded prospective outcomes for ranking — aldri rekonstruert backtest som primærkilde.

Feasibility (did the athlete do the session?) is not physiological effectiveness.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from .canonical_prospective_observation import CanonicalProspectiveObservationService
from .outcome_maturity import EVALUATED, is_usable_status
from .recommendation_utility_evaluator import RecommendationUtilityEvaluator
from .sample_sufficiency_policy import SampleSufficiencyPolicy

_FEASIBILITY_POINTS = {
    "followed": 80.0,
    "completed": 80.0,
    "modified": 60.0,
    "partial": 55.0,
    "replaced": 40.0,
    "unplanned": 45.0,
    "skipped": 20.0,
    "missed": 20.0,
}


class ProspectiveOutcomeLookup:
    def __init__(self, db: Session):
        self.db = db
        self._canonical = CanonicalProspectiveObservationService(db)
        self._utility = RecommendationUtilityEvaluator(db)
        self._sufficiency = SampleSufficiencyPolicy()

    def historical_by_type(self, *, as_of: Optional[date] = None) -> Dict[str, Any]:
        """Kun kanoniske observasjoner før as_of. Superseded rader teller ikke dobbelt."""
        today = as_of or date.today()
        observations = self._canonical.resolve(end=as_of, today=today) if as_of else self._canonical.resolve(today=today)
        if as_of is not None:
            observations = [row for row in observations if row["as_of_date"] < as_of.isoformat()]

        buckets: Dict[str, Dict[str, Any]] = {}
        for observation in observations:
            wtype = observation.get("recommended_workout_type") or "unknown"
            bucket = buckets.setdefault(
                wtype,
                {
                    "feasibility": [],
                    "feasibility_dates": [],
                    "feasibility_weights": [],
                    "effectiveness": [],
                    "effectiveness_dates": [],
                    "effectiveness_weights": [],
                    "feedback": 0,
                },
            )
            obs_date = date.fromisoformat(observation["as_of_date"])
            weight = float(observation.get("evidence_weight") or 0.0)
            status = (observation.get("execution_status") or "").lower()
            execution_state = (observation.get("maturity_status") or {}).get("execution")
            if status != "pending" and execution_state == EVALUATED and status in _FEASIBILITY_POINTS:
                score = _FEASIBILITY_POINTS[status]
                adherence = observation.get("overall_adherence")
                if adherence is not None and observation.get("match_source") == "explicit_execution":
                    score = 0.5 * score + 0.5 * (float(adherence) * 100.0)
                bucket["feasibility"].append(max(0.0, min(100.0, score)))
                bucket["feasibility_dates"].append(obs_date)
                bucket["feasibility_weights"].append(weight if weight > 0 else 1.0)

            utility = self._utility.evaluate_for_observation(observation, today=today)
            if is_usable_status(utility.get("short_term_maturity")) and utility.get("short_term_utility") is not None:
                # Physiological response only — adherence is not added here.
                bucket["effectiveness"].append(float(utility["short_term_utility"]) * 100.0)
                bucket["effectiveness_dates"].append(obs_date)
                eff_weight = weight if observation.get("match_source") == "explicit_execution" else min(weight, 0.35)
                bucket["effectiveness_weights"].append(eff_weight if eff_weight > 0 else 0.35)
            if observation.get("subjective_feedback"):
                bucket["feedback"] += 1

        result: Dict[str, Any] = {}
        for wtype, bucket in buckets.items():
            feasibility = _mean_block(
                self._sufficiency,
                domain="execution_patterns",
                values=bucket["feasibility"],
                dates=bucket["feasibility_dates"],
                weights=bucket["feasibility_weights"],
                as_of=today,
            )
            effectiveness = _mean_block(
                self._sufficiency,
                domain="workout_effectiveness",
                values=bucket["effectiveness"],
                dates=bucket["effectiveness_dates"],
                weights=bucket["effectiveness_weights"],
                as_of=today,
            )
            if feasibility["sample_count"] == 0 and effectiveness["sample_count"] == 0 and bucket["feedback"] == 0:
                continue
            usable = bool(effectiveness["may_override_defaults"] and effectiveness["value"] is not None)
            result[wtype] = {
                # Ranking may read `value` only when usable. That value is effectiveness, not adherence.
                "value": effectiveness["value"] if usable else None,
                "sample_count": effectiveness["sample_count"],
                "effective_sample_count": effectiveness["effective_sample_count"],
                "spread_days": effectiveness["spread_days"],
                "level": effectiveness["level"],
                "confidence": effectiveness["confidence"],
                "source": "prospective_records",
                "usable": usable,
                "feasibility": feasibility,
                "effectiveness": effectiveness,
                "subjective_feedback": {
                    "sample_count": bucket["feedback"],
                    "provenance": "athlete_feedback",
                    "ground_truth": False,
                    "replaces_objective_data": False,
                },
            }
        return result


def _mean_block(
    policy: SampleSufficiencyPolicy,
    *,
    domain: str,
    values: List[float],
    dates: List[date],
    weights: List[float],
    as_of: date,
) -> Dict[str, Any]:
    sufficiency = policy.assess_weighted(
        domain=domain,
        observation_dates=dates,
        evidence_weights=weights,
        as_of=as_of,
    )
    value = round(sum(values) / len(values), 1) if values else None
    confidence = None
    if sufficiency["sample_count"]:
        confidence = round(min(0.85, sufficiency["effective_sample_count"] / 20.0), 2)
    return {
        "value": value,
        "sample_count": sufficiency["sample_count"],
        "effective_sample_count": sufficiency["effective_sample_count"],
        "spread_days": sufficiency["spread_days"],
        "level": sufficiency["level"],
        "evidence_weight_sum": sufficiency.get("evidence_weight_sum"),
        "may_override_defaults": sufficiency["may_override_defaults"],
        "confidence": confidence,
        "floors": sufficiency["floors"],
    }
