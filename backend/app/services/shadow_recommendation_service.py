"""Shadow-mode recommendations — never mutate the active plan."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..database.models.coaching_v5 import ShadowRecommendation
from ..storage import DataStorage
from .coaching_tx import finalize_write
from .next_best_workout_service import NextBestWorkoutService
from .ppap_metrics_service import PpapMetricsService


class ShadowRecommendationService:
    def __init__(self, db: Session, storage: Optional[DataStorage] = None):
        self.db = db
        self.storage = storage

    def record_shadow(
        self,
        *,
        day: date,
        production: Dict[str, Any],
        production_recommendation_id: Optional[int] = None,
        model_key: str = "ranker_shadow",
        model_version: str = "experimental",
        commit: bool = True,
    ) -> Dict[str, Any]:
        """Run a conservative alternate preference and persist separately."""
        shadow_type = self._shadow_choice(production)
        existing = (
            self.db.query(ShadowRecommendation)
            .filter(
                ShadowRecommendation.as_of_date == day,
                ShadowRecommendation.model_key == model_key,
                ShadowRecommendation.model_version == model_version,
                ShadowRecommendation.production_recommendation_id == production_recommendation_id,
            )
            .first()
        )
        if existing:
            return {**self._to_dict(existing), "idempotent_reuse": True}

        row = ShadowRecommendation(
            as_of_date=day,
            production_recommendation_id=production_recommendation_id,
            model_key=model_key,
            model_version=model_version,
            production_workout_type=production.get("workout_type"),
            shadow_workout_type=shadow_type,
            payload_json={
                "schema_version": 1,
                "production": production.get("workout_type"),
                "shadow": shadow_type,
                "note": "Shadow output does not affect the active plan.",
            },
            config_hash=(production.get("context_summary") or {}).get("as_of_date"),
        )
        self.db.add(row)
        finalize_write(self.db, commit=commit)
        if commit:
            self.db.refresh(row)
        return self._to_dict(row)

    @staticmethod
    def _shadow_choice(production: Dict[str, Any]) -> str:
        # Transparent alternate: if production is easy, shadow prefers quality when eligible;
        # otherwise shadow prefers the safer easy option. Not a second physiology engine.
        candidates = production.get("candidate_workouts") or []
        eligible = [c.get("workout_type") for c in candidates if c.get("eligible")]
        prod = production.get("workout_type")
        if prod in {"easy_run", "recovery_run", "rest"}:
            for cand in ("threshold", "long_run", "race_pace"):
                if cand in eligible:
                    return cand
            return prod or "easy_run"
        return "easy_run"

    @staticmethod
    def _to_dict(row: ShadowRecommendation) -> Dict[str, Any]:
        return {
            "id": row.id,
            "as_of_date": row.as_of_date.isoformat() if row.as_of_date else None,
            "production_recommendation_id": row.production_recommendation_id,
            "model_key": row.model_key,
            "model_version": row.model_version,
            "production": row.production_workout_type,
            "shadow": row.shadow_workout_type,
            "payload": row.payload_json,
            "note": "Shadow recommendation never modifies the active plan.",
        }
