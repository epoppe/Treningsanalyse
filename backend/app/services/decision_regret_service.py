"""Observasjonell regret-proxy. Dette er ikke et ekte kontrafaktisk utfall."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..storage import DataStorage
from .recommendation_ledger_service import RecommendationLedgerService
from .recommendation_outcome_service import RecommendationOutcomeService
from .workout_effectiveness_service import WorkoutEffectivenessService


class DecisionRegretService:
    def __init__(self, db: Session, storage: Optional[DataStorage] = None):
        self.db = db
        self.storage = storage
        self._ledger = RecommendationLedgerService(db)
        self._outcomes = RecommendationOutcomeService(db, storage)
        self._effectiveness = WorkoutEffectivenessService(db, storage)

    def assess(self, record_id: int) -> Dict[str, Any]:
        record = self._ledger.get_recommendation(record_id)
        if record is None:
            return {"status": "not_found", "record_id": record_id}
        observed = self._outcomes.evaluate_recorded_recommendation(record_id)
        recommended = record["recommended_workout_type"]
        actual = observed.get("actual")
        as_of = date.fromisoformat(record["as_of_date"])
        expected = {
            recommended: self._historical_expected(recommended, as_of),
        }
        if actual and actual != recommended:
            expected[actual] = self._historical_expected(actual, as_of)

        assessment = "inconclusive"
        confidence = 0.25
        rec_exp = expected.get(recommended) or {}
        act_exp = expected.get(actual) or {}
        rec_n = rec_exp.get("sample_count") or 0
        act_n = act_exp.get("sample_count") or 0
        if rec_n >= 6 and act_n >= 6 and actual and actual != recommended:
            rec_q = rec_exp.get("mean_quality")
            act_q = act_exp.get("mean_quality")
            if rec_q is not None and act_q is not None:
                if act_q > rec_q + 8:
                    assessment = "supports_actual"
                    confidence = 0.45
                elif rec_q > act_q + 8:
                    assessment = "supports_original"
                    confidence = 0.45
        elif observed.get("outcome") == "favorable_response" and observed.get("adherence"):
            assessment = "supports_original"
            confidence = 0.35
        elif observed.get("outcome") == "unfavorable_response" and not observed.get("adherence"):
            assessment = "inconclusive"
            confidence = 0.2

        return {
            "recommended": recommended,
            "actual": actual,
            "observed_outcome": observed.get("outcome"),
            "historical_expected_outcomes": expected,
            "regret_assessment": assessment,
            "confidence": round(confidence, 2),
            "method": "observational_counterfactual_proxy",
            "note": "Not a true counterfactual. Alternative outcomes were not observed.",
        }

    def _historical_expected(self, workout_type: str, as_of: date) -> Dict[str, Any]:
        mapped = {
            "easy_run": "easy_run",
            "recovery_run": "easy_run",
            "long_run": "long_run",
            "threshold": "threshold",
            "vo2_intervals": "vo2_intervals",
            "race_pace": "threshold",
            "easy_aerobic": "easy_run",
            "tempo": "threshold",
        }.get(workout_type, workout_type)
        try:
            result = self._effectiveness.analyze(mapped, end_date=as_of)
        except Exception:
            result = {}
        lag = (result.get("historical_response") or {}).get("21d") or {}
        change = lag.get("mean_threshold_pace_change_sec_km")
        mean_quality = None
        if change is not None:
            mean_quality = max(0.0, min(100.0, 50.0 - float(change) * 2.0))
        return {
            "workout_type": workout_type,
            "sample_count": result.get("sample_count") or 0,
            "mean_quality": mean_quality,
            "source": "historical_observational",
            "as_of": as_of.isoformat(),
        }
