"""Transparent personal recovery-cost ranges — not exact predictions."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..database.models.coaching_v5 import RecommendationExecution, RecommendationRecord
from .personalization_evidence_policy import PersonalizationEvidencePolicy
from .ppap_metrics_service import PpapMetricsService


DEFAULT_RANGES = {
    "easy_run": {"expected_recovery_days": [0, 1], "confidence": "moderate"},
    "recovery_run": {"expected_recovery_days": [0, 1], "confidence": "moderate"},
    "long_run": {"expected_recovery_days": [1, 2], "confidence": "moderate"},
    "threshold": {"expected_recovery_days": [1, 2], "confidence": "moderate"},
    "vo2_intervals": {"expected_recovery_days": [1, 3], "confidence": "moderate"},
    "race_pace": {"expected_recovery_days": [1, 2], "confidence": "low"},
    "race": {"expected_recovery_days": [3, 7], "confidence": "moderate"},
    "strength": {"expected_recovery_days": [1, 2], "confidence": "low"},
    "cycling": {"expected_recovery_days": [0, 1], "confidence": "low"},
}


class RecoveryCostService:
    def __init__(self, db: Session, ppap: Optional[PpapMetricsService] = None):
        self.db = db
        self._ppap = ppap or PpapMetricsService(db, None)
        self._policy = PersonalizationEvidencePolicy()

    def estimate(self, workout_type: str, *, as_of: Optional[date] = None) -> Dict[str, Any]:
        as_of = as_of or date.today()
        base = dict(DEFAULT_RANGES.get(workout_type, {"expected_recovery_days": [1, 2], "confidence": "low"}))
        personal = self._personal_days(workout_type, as_of)
        level = self._policy.assess(
            sample_count=personal.get("sample_count", 0),
            evidence_strength=0.4 if personal.get("sample_count", 0) >= 8 else 0.2,
            prospective=True,
            as_of=as_of,
        )
        if level["may_override_defaults"] and personal.get("range"):
            return {
                "workout_type": workout_type,
                "expected_recovery_days": personal["range"],
                "confidence": "moderate" if level["level"] != "PERSONAL_STRONG" else "high",
                "source": "personal",
                "sample_count": personal["sample_count"],
                "personalization_level": level["level"],
                "note": "Range estimate from post-session markers — not causal.",
            }
        return {
            "workout_type": workout_type,
            "expected_recovery_days": base["expected_recovery_days"],
            "confidence": base["confidence"],
            "source": "default",
            "sample_count": personal.get("sample_count", 0),
            "personalization_level": level["level"],
            "note": "Default recovery envelope until sufficient prospective evidence.",
        }

    def summary(self, *, as_of: Optional[date] = None) -> Dict[str, Any]:
        types = ["easy_run", "long_run", "threshold", "vo2_intervals", "race", "strength", "cycling"]
        return {t: self.estimate(t, as_of=as_of) for t in types}

    def _personal_days(self, workout_type: str, as_of: date) -> Dict[str, Any]:
        rows = (
            self.db.query(RecommendationExecution, RecommendationRecord)
            .outerjoin(RecommendationRecord, RecommendationExecution.recommendation_id == RecommendationRecord.id)
            .limit(200)
            .all()
        )
        recovery_hits = []
        for exec_row, rec in rows:
            planned = exec_row.planned_type or (rec.recommended_workout_type if rec else None)
            if planned != workout_type:
                continue
            # Use adherence / analysis as weak proxy; prefer next-day HRV when linked activity date known
            if exec_row.overall_adherence is not None and exec_row.overall_adherence < 0.6:
                recovery_hits.append(2.0)
            else:
                recovery_hits.append(1.0 if planned in {"threshold", "vo2_intervals"} else 0.5)
        n = len(recovery_hits)
        if n < 5:
            return {"sample_count": n, "range": None}
        mean = sum(recovery_hits) / n
        lo = max(0, int(mean))
        hi = max(lo + 1, int(round(mean + 1)))
        return {"sample_count": n, "range": [lo, hi]}
