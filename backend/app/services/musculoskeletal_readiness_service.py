"""Transparent muskel-/skjelett-readiness. Ikke skadeprediksjon eller diagnose."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session, joinedload

from ..database.models.activity import Activity
from ..database.models.coaching_v5 import AthleteFeedback
from ..storage import DataStorage
from ..utils.activity_filters import is_running_activity
from .cross_training_load_service import CrossTrainingLoadService
from .ppap_metrics_service import PpapMetricsService

PAIN_CAUTION = 3
PAIN_LOW = 5


class MusculoskeletalReadinessService:
    def __init__(
        self,
        db: Session,
        storage: Optional[DataStorage] = None,
        ppap: Optional[PpapMetricsService] = None,
    ):
        self.db = db
        self.storage = storage
        self._ppap = ppap or PpapMetricsService(db, storage)
        self._cross = CrossTrainingLoadService(db)

    def assess(self, day: Optional[date] = None) -> Dict[str, Any]:
        day = day or date.today()
        evidence: List[str] = []
        score = 80.0
        confidence = 0.4

        runs = self._runs(day, 7)
        prior = self._runs(day - timedelta(days=7), 7)
        vol7 = sum((a.duration or 0) for a in runs) / 60.0
        vol_prior = sum((a.duration or 0) for a in prior) / 60.0
        if vol_prior and vol7 > vol_prior * 1.4:
            score -= 15
            evidence.append("recent_running_volume_spike")
        hard = [a for a in runs if (a.total_training_effect or 0) >= 3.5]
        if len(hard) >= 3:
            score -= 15
            evidence.append("high_recent_intensity")
        long_runs = [a for a in runs if (a.duration or 0) >= 75 * 60]
        if long_runs:
            evidence.append("recent_long_run_load")
            if (day - long_runs[-1].start_time.date()).days <= 1:
                score -= 10

        cadences = [float(a.average_running_cadence) for a in runs if a.average_running_cadence]
        if len(cadences) >= 3:
            mean_c = sum(cadences) / len(cadences)
            latest = cadences[0]
            if mean_c and abs(latest - mean_c) / mean_c > 0.08:
                score -= 8
                evidence.append("cadence_form_change")
            confidence = max(confidence, 0.55)

        feedback = self._latest_feedback(day)
        if feedback:
            confidence = max(confidence, 0.6)
            if feedback.rpe and feedback.rpe >= 8:
                score -= 8
                evidence.append("high_rpe")
            if feedback.pain is not None:
                if feedback.pain > PAIN_LOW:
                    score = min(score, 35)
                    evidence.append("pain_above_conservative_threshold")
                elif feedback.pain > PAIN_CAUTION:
                    score -= 20
                    evidence.append("pain_caution")
            if feedback.legs == "heavy":
                score -= 8
                evidence.append("heavy_legs")

        strength = self._recent_strength(day)
        if strength:
            score -= 12
            evidence.append("recent_heavy_leg_strength")

        if not runs and not feedback:
            evidence.append("sparse_musculoskeletal_inputs")
            confidence = min(confidence, 0.3)

        if score >= 70:
            label = "good"
        elif score >= 50:
            label = "caution"
        else:
            label = "low"
        return {
            "musculoskeletal_readiness": label,
            "evidence": evidence,
            "confidence": round(confidence, 2),
            "guardrail": "conservative_easy_or_rest" if label == "low" else (
                "avoid_hard_if_pain" if label == "caution" else None
            ),
            "note": "Not a medical diagnosis or injury prediction.",
        }

    def _runs(self, end: date, window: int) -> List[Activity]:
        start = end - timedelta(days=window - 1)
        rows = (
            self.db.query(Activity)
            .options(joinedload(Activity.activity_type))
            .filter(
                and_(
                    func.date(Activity.start_time) >= start,
                    func.date(Activity.start_time) <= end,
                )
            )
            .order_by(Activity.start_time.desc())
            .all()
        )
        return [a for a in rows if is_running_activity(a, include_treadmill=True)]

    def _latest_feedback(self, day: date) -> Optional[AthleteFeedback]:
        return (
            self.db.query(AthleteFeedback)
            .filter(func.date(AthleteFeedback.recorded_at) <= day)
            .order_by(AthleteFeedback.recorded_at.desc())
            .first()
        )

    def _recent_strength(self, day: date) -> bool:
        start = day - timedelta(days=1)
        rows = (
            self.db.query(Activity)
            .options(joinedload(Activity.activity_type))
            .filter(
                and_(
                    func.date(Activity.start_time) >= start,
                    func.date(Activity.start_time) <= day,
                )
            )
            .all()
        )
        for activity in rows:
            analysis = self._cross.analyze(activity)
            if analysis.get("modality") == "strength" and analysis.get("musculoskeletal_load") == "high":
                return True
        return False
