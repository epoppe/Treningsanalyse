"""Personalized utility weights — only after sufficient prospective evidence."""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..database.models.coaching_v5 import RecommendationExecution
from .statistical_uncertainty import evidence_band

DEFAULT_WEIGHTS = {
    "fitness_benefit_weight": 0.30,
    "recovery_cost_weight": 0.25,
    "execution_feasibility_weight": 0.20,
    "goal_alignment_weight": 0.15,
    "consistency_adherence_weight": 0.10,
}

MIN_PROSPECTIVE_N = 20


class AthleteUtilityProfile:
    def __init__(self, db: Session):
        self.db = db

    def build(self, *, prospective_n: Optional[int] = None) -> Dict[str, Any]:
        n = prospective_n
        if n is None:
            n = self.db.query(RecommendationExecution).count()
        if n < MIN_PROSPECTIVE_N:
            return {
                **DEFAULT_WEIGHTS,
                "source": "default",
                "evidence_strength": 0.25,
                "statistical_support": "weak",
                "sample_count": n,
                "note": "Personal weights require sufficient prospective execution evidence.",
            }

        # Lightweight personal tilt from adherence / recovery-heavy executions
        completed = (
            self.db.query(RecommendationExecution)
            .filter(RecommendationExecution.execution_status.in_(["completed", "modified", "partial"]))
            .count()
        )
        adherence_rate = completed / max(1, n)
        weights = dict(DEFAULT_WEIGHTS)
        if adherence_rate < 0.55:
            weights["execution_feasibility_weight"] = min(0.35, weights["execution_feasibility_weight"] + 0.08)
            weights["fitness_benefit_weight"] = max(0.18, weights["fitness_benefit_weight"] - 0.05)
        elif adherence_rate > 0.8:
            weights["fitness_benefit_weight"] = min(0.38, weights["fitness_benefit_weight"] + 0.05)
            weights["execution_feasibility_weight"] = max(0.12, weights["execution_feasibility_weight"] - 0.03)
        # Renormalize
        total = sum(weights.values())
        weights = {k: round(v / total, 3) for k, v in weights.items()}
        strength = min(0.85, 0.3 + 0.01 * n)
        return {
            **weights,
            "source": "personal",
            "evidence_strength": round(strength, 2),
            "statistical_support": evidence_band(sample_count=n, effect_size=0.2),
            "sample_count": n,
            "note": "Weights are transparent components — not a black box.",
        }
