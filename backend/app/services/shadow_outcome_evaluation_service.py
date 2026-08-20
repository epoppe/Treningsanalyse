"""Prospective evaluation of shadow vs production vs actual outcomes."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..database.models.coaching_v5 import RecommendationRecord, ShadowRecommendation
from .recommendation_outcome_service import RecommendationOutcomeService
from .recommendation_utility_evaluator import RecommendationUtilityEvaluator


class ShadowOutcomeEvaluationService:
    def __init__(self, db: Session, storage=None):
        self.db = db
        self.storage = storage
        self._utility = RecommendationUtilityEvaluator(db, storage)
        self._outcomes = RecommendationOutcomeService(db, storage)

    def evaluate_range(self, *, start: date, end: date) -> Dict[str, Any]:
        shadows = (
            self.db.query(ShadowRecommendation)
            .filter(ShadowRecommendation.as_of_date >= start, ShadowRecommendation.as_of_date <= end)
            .order_by(ShadowRecommendation.as_of_date.asc())
            .all()
        )
        comparisons: List[Dict[str, Any]] = []
        for shadow in shadows:
            outcome = self._outcomes.simulate_as_of(shadow.as_of_date)
            actual = outcome.get("actual")
            prod_util = self._utility.evaluate(
                recommended_type=shadow.production_workout_type,
                actual_type=actual,
                as_of=shadow.as_of_date,
            )
            shadow_util = self._utility.evaluate(
                recommended_type=shadow.shadow_workout_type,
                actual_type=actual,
                as_of=shadow.as_of_date,
            )
            comparisons.append(
                {
                    "as_of_date": shadow.as_of_date.isoformat(),
                    "production": shadow.production_workout_type,
                    "shadow": shadow.shadow_workout_type,
                    "actual": actual,
                    "production_utility": prod_util,
                    "shadow_utility": shadow_util,
                    "shadow_plausible_better": bool(shadow_util.get("plausible_better_despite_mismatch"))
                    or (
                        (shadow_util.get("short_term_utility") or 0)
                        > (prod_util.get("short_term_utility") or 0) + 0.05
                    ),
                }
            )

        # Confirm shadow never became an active production plan driver
        shadow_recs_active = (
            self.db.query(RecommendationRecord)
            .filter(RecommendationRecord.is_shadow.is_(True), RecommendationRecord.is_active.is_(True))
            .count()
        )
        return {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "comparisons": comparisons,
            "n": len(comparisons),
            "shadow_active_plan_violations": shadow_recs_active,
            "note": "Shadow outcomes are observational comparisons — not counterfactual truth.",
        }
