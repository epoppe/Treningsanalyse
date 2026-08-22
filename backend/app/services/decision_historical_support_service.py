"""Historical support bullets for WhyThisWorkout — observational, not causal."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..database.models.coaching_v5 import RecommendationRecord
from ..storage import DataStorage
from .recommendation_ledger_service import RecommendationLedgerService
from .training_response_service import TrainingResponseService

WORKOUT_OUTCOME_HINTS = {
    "threshold": ("threshold_volume", "threshold_pace"),
    "vo2_intervals": ("high_intensity_volume", "vo2max"),
    "easy_run": ("easy_volume", "easy_efficiency"),
    "long_run": ("easy_volume", "durability"),
    "recovery_run": ("easy_volume", "hrv"),
    "race_pace": ("high_intensity_volume", "threshold_pace"),
}


class DecisionHistoricalSupportService:
    def __init__(self, db: Session, storage: Optional[DataStorage] = None):
        self.db = db
        self.storage = storage
        self._ledger = RecommendationLedgerService(db)
        self._training = TrainingResponseService(db, storage)

    def build(
        self,
        *,
        workout_type: Optional[str],
        as_of_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        day = as_of_date or date.today()
        workout_type = workout_type or "easy_run"
        items: List[Dict[str, Any]] = []

        rec_count = (
            self.db.query(RecommendationRecord)
            .filter(
                RecommendationRecord.recommended_workout_type == workout_type,
                RecommendationRecord.is_shadow.is_(False),
            )
            .count()
        )
        if rec_count:
            items.append(
                {
                    "kind": "ledger",
                    "label": "Tidligere anbefalinger",
                    "detail": f"{rec_count} lagrede anbefalinger av {workout_type.replace('_', ' ')}",
                    "evidence": "supported" if rec_count >= 12 else "emerging" if rec_count >= 5 else "insufficient",
                }
            )

        latest = self._ledger.get_latest_active_recommendation(as_of_date=day)
        if latest and latest.get("recommended_workout_type") == workout_type:
            conf = latest.get("decision_confidence")
            if conf is not None:
                items.append(
                    {
                        "kind": "decision",
                        "label": "Dagens beslutning",
                        "detail": f"Modell-konfidens {round(float(conf) * 100)}% for denne anbefalingen",
                        "evidence": "supported" if conf >= 0.65 else "emerging" if conf >= 0.45 else "insufficient",
                    }
                )

        hints = WORKOUT_OUTCOME_HINTS.get(workout_type)
        if hints:
            stimulus_hint, outcome_hint = hints
            raw = self._training.analyze_responses(end_date=day, lookback_days=365)
            hit = next(
                (
                    r
                    for r in (raw.get("relationships") or [])
                    if r.get("stimulus") == stimulus_hint and r.get("outcome") == outcome_hint
                ),
                None,
            )
            if hit:
                support = str(hit.get("statistical_support") or "weak")
                items.append(
                    {
                        "kind": "training_response",
                        "label": "Historisk responsmønster",
                        "detail": (
                            f"{stimulus_hint.replace('_', ' ')} har vært assosiert med "
                            f"{outcome_hint.replace('_', ' ')} (lag {hit.get('lag_days')}d)"
                        ),
                        "evidence": {
                            "strong": "strong",
                            "moderate": "supported",
                            "weak": "emerging",
                        }.get(support, "insufficient"),
                        "relationship": hit.get("relationship"),
                        "sample_count": hit.get("sample_count"),
                    }
                )

        return {
            "status": "ok",
            "as_of": day.isoformat(),
            "workout_type": workout_type,
            "items": items,
            "disclaimer": "Historical support describes past patterns — not proof this workout is optimal today.",
        }
