"""Prospective evaluation of shadow vs production vs actual outcomes."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..database.models.coaching_v5 import RecommendationRecord, ShadowRecommendation
from .canonical_prospective_observation import CanonicalProspectiveObservationService
from .recommendation_utility_evaluator import RecommendationUtilityEvaluator


class ShadowOutcomeEvaluationService:
    def __init__(self, db: Session, storage=None):
        self.db = db
        self.storage = storage
        self._utility = RecommendationUtilityEvaluator(db, storage)
        self._canonical = CanonicalProspectiveObservationService(db)

    def evaluate_range(self, *, start: date, end: date) -> Dict[str, Any]:
        shadows = (
            self.db.query(ShadowRecommendation)
            .filter(ShadowRecommendation.as_of_date >= start, ShadowRecommendation.as_of_date <= end)
            .order_by(ShadowRecommendation.as_of_date.asc())
            .all()
        )
        production = {
            row["as_of_date"]: row
            for row in self._canonical.resolve(start=start, end=end, today=end)
        }
        comparisons: List[Dict[str, Any]] = []
        for shadow in shadows:
            obs = production.get(shadow.as_of_date.isoformat())
            if obs is None:
                comparisons.append(
                    {
                        "as_of_date": shadow.as_of_date.isoformat(),
                        "production": shadow.production_workout_type,
                        "shadow": shadow.shadow_workout_type,
                        "actual": None,
                        "match_source": "none",
                        "shadow_plausible_better": False,
                        "status": "no_production_observation",
                        "note": "Shadow rows are not production evidence and do not invent an activity match.",
                    }
                )
                continue
            actual = obs.get("actual_type")
            prod_util = self._utility.evaluate_for_observation(obs, today=end)
            shadow_util = self._utility.evaluate_for_observation(
                obs,
                today=end,
                recommended_type=shadow.shadow_workout_type,
            )
            comparisons.append(
                {
                    "as_of_date": shadow.as_of_date.isoformat(),
                    "production": obs.get("recommended_workout_type"),
                    "shadow": shadow.shadow_workout_type,
                    "actual": actual,
                    "match_source": obs.get("match_source"),
                    "match_confidence": obs.get("match_confidence"),
                    "production_utility": prod_util,
                    "shadow_utility": shadow_util,
                    "shadow_plausible_better": bool(shadow_util.get("plausible_better_despite_mismatch"))
                    or (
                        (shadow_util.get("short_term_utility") or 0)
                        > (prod_util.get("short_term_utility") or 0) + 0.05
                    ),
                    "status": "compared",
                    "note": "Observational comparison against the canonical production observation.",
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
