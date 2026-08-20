"""Historisk validering av coaching-signaler uten fremtidslekkasje (as-of date)."""

from __future__ import annotations

from datetime import date, timedelta
from statistics import mean
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..storage import DataStorage
from .coaching_decision_metrics_service import CoachingDecisionMetricsService
from .coaching_session_types import HARD_SESSION_TYPES
from .next_best_workout_service import NextBestWorkoutService
from .ppap_metrics_service import PpapMetricsService
from .session_classifier_service import SessionClassifierService


class CoachingBacktestService:
    """Evaluerer prediktiv verdi av readiness, fatigue og workout-anbefalinger."""

    def __init__(
        self,
        db: Session,
        storage: Optional[DataStorage] = None,
    ):
        self.db = db
        self.storage = storage
        self._ppap = PpapMetricsService(db, storage)
        self._decision = CoachingDecisionMetricsService(db, self._ppap)
        self._next_workout = NextBestWorkoutService(db, storage, self._ppap)
        self._classifier = SessionClassifierService(db, storage)

    def evaluate_period(
        self,
        *,
        start_date: date,
        end_date: date,
        step_days: int = 7,
    ) -> Dict[str, Any]:
        evaluations: List[Dict[str, Any]] = []
        current = start_date
        while current <= end_date:
            evaluations.append(self._evaluate_as_of(current))
            current += timedelta(days=step_days)

        return {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "step_days": step_days,
            "evaluations": evaluations,
            "summary": self._summarize(evaluations),
        }

    def _evaluate_as_of(self, as_of: date) -> Dict[str, Any]:
        """Kun data tilgjengelig på as_of — ingen fremtidig informasjon."""
        snapshot = self._decision.build_coaching_snapshot(as_of)
        recommendation = self._next_workout.recommend(as_of)

        forward_7 = self._forward_outcomes(as_of, as_of + timedelta(days=7))
        forward_28 = self._forward_outcomes(as_of, as_of + timedelta(days=28))

        readiness = snapshot.get("readiness_by_event", {}).get("5k")
        hard_quality = forward_7.get("next_hard_session_quality")
        hrv_change = forward_7.get("hrv_delta_pct_change")

        return {
            "as_of_date": as_of.isoformat(),
            "readiness_5k": readiness,
            "recommended_workout": recommendation.get("workout_type"),
            "recommendation_confidence": recommendation.get("confidence"),
            "forward_7d": forward_7,
            "forward_28d": forward_28,
            "signals": {
                "readiness_vs_hard_quality": self._score_alignment(readiness, hard_quality),
                "fatigue_vs_hrv": self._fatigue_signal_score(as_of, hrv_change),
                "recommendation_vs_actual": self._recommendation_match(
                    recommendation.get("workout_type"),
                    forward_7.get("dominant_session_type"),
                ),
            },
        }

    def _forward_outcomes(self, start: date, end: date) -> Dict[str, Any]:
        from sqlalchemy import and_, func

        from ..database.models import HRV
        from ..database.models.activity import Activity
        from ..utils.activity_filters import is_running_activity

        hrv_start = self._ppap.get_hrv_delta_pct(start)
        hrv_end = self._ppap.get_hrv_delta_pct(end)

        activities = (
            self.db.query(Activity)
            .filter(
                and_(
                    func.date(Activity.start_time) > start,
                    func.date(Activity.start_time) <= end,
                )
            )
            .order_by(Activity.start_time)
            .all()
        )

        session_types: List[str] = []
        first_hard_quality: Optional[float] = None
        for activity in activities:
            if not is_running_activity(activity):
                continue
            classification = self._classifier.classify_activity(activity, end_date=end)
            st = classification.get("session_type", "unknown")
            session_types.append(st)
            if st in HARD_SESSION_TYPES and first_hard_quality is None:
                first_hard_quality = self._decision.compute_long_run_quality(activity)
                if first_hard_quality is None:
                    first_hard_quality = classification.get("confidence", 0) * 100

        dominant = max(set(session_types), key=session_types.count) if session_types else None

        return {
            "session_count": len(session_types),
            "dominant_session_type": dominant,
            "next_hard_session_quality": first_hard_quality,
            "hrv_delta_pct_change": (
                (hrv_end - hrv_start) if hrv_start is not None and hrv_end is not None else None
            ),
        }

    def _score_alignment(
        self,
        readiness: Optional[float],
        hard_quality: Optional[float],
    ) -> Optional[str]:
        if readiness is None or hard_quality is None:
            return None
        if readiness >= 70 and hard_quality >= 70:
            return "aligned_positive"
        if readiness < 50 and hard_quality < 60:
            return "aligned_negative"
        return "mixed"

    def _fatigue_signal_score(
        self,
        as_of: date,
        hrv_change: Optional[float],
    ) -> Optional[str]:
        tsb = self._ppap.get_tsb(as_of)
        if tsb is None or hrv_change is None:
            return None
        if tsb < -15 and hrv_change < -5:
            return "fatigue_signal_confirmed"
        if tsb > 0 and hrv_change > 0:
            return "recovery_signal_confirmed"
        return "inconclusive"

    def _recommendation_match(
        self,
        recommended: Optional[str],
        actual: Optional[str],
    ) -> Optional[str]:
        if not recommended or not actual:
            return None
        mapping = {
            "easy_run": {"easy_aerobic", "recovery_run", "steady", "long_aerobic"},
            "recovery_run": {"recovery_run", "easy_aerobic"},
            "threshold": {"threshold", "tempo", "steady"},
            "vo2_intervals": {"vo2_intervals", "anaerobic"},
            "rest": set(),
        }
        compatible = mapping.get(recommended, set())
        if actual in compatible or actual == recommended:
            return "match"
        return "mismatch"

    def _summarize(self, evaluations: List[Dict[str, Any]]) -> Dict[str, Any]:
        alignments = [e["signals"].get("readiness_vs_hard_quality") for e in evaluations]
        matches = [e["signals"].get("recommendation_vs_actual") for e in evaluations]
        aligned = sum(1 for a in alignments if a in {"aligned_positive", "aligned_negative"})
        matched = sum(1 for m in matches if m == "match")
        valid_align = sum(1 for a in alignments if a is not None)
        valid_match = sum(1 for m in matches if m is not None)

        return {
            "evaluation_count": len(evaluations),
            "readiness_alignment_rate": round(aligned / valid_align, 2) if valid_align else None,
            "recommendation_match_rate": round(matched / valid_match, 2) if valid_match else None,
        }
