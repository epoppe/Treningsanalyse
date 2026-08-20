"""Kobler historiske anbefalinger til faktiske utfall — uten kausal overtolkning."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session, joinedload

from ..database.models import HRV, RestingHeartRate
from ..database.models.activity import Activity
from ..storage import DataStorage
from ..utils.activity_filters import is_running_activity
from .next_best_workout_service import NextBestWorkoutService
from .ppap_metrics_service import PpapMetricsService
from .recommendation_ledger_service import RecommendationLedgerService
from .session_classifier_service import SessionClassifierService
from .session_quality_service import SessionQualityService

WORKOUT_TO_SESSION = {
    "rest": set(),
    "recovery_run": {"recovery_run", "easy_aerobic"},
    "easy_run": {"easy_aerobic", "recovery_run", "steady", "long_aerobic"},
    "long_run": {"long_aerobic", "easy_aerobic"},
    "threshold": {"threshold", "tempo", "steady"},
    "vo2_intervals": {"vo2_intervals", "anaerobic"},
    "race_pace": {"race", "threshold", "tempo"},
}


class RecommendationOutcomeService:
    """Evaluerer anbefaling vs faktisk økt og påfølgende respons."""

    def __init__(
        self,
        db: Session,
        storage: Optional[DataStorage] = None,
    ):
        self.db = db
        self.storage = storage
        self._ppap = PpapMetricsService(db, storage)
        self._next = NextBestWorkoutService(db, storage, self._ppap)
        self._classifier = SessionClassifierService(db, storage)
        self._quality = SessionQualityService(db, storage, self._ppap)
        self._ledger = RecommendationLedgerService(db)

    def simulate_as_of(self, recommendation_date: date) -> Dict[str, Any]:
        """Backtest: regenerer dagens modell mot historiske data. Ikke prospective."""
        payload = self.evaluate_as_of(recommendation_date)
        payload["evaluation_kind"] = "backtest"
        payload["note"] = (
            "Backtest regenerates the current model as-of the date. "
            "It is not what the live model recorded at the time."
        )
        return payload

    def evaluate_as_of(self, recommendation_date: date) -> Dict[str, Any]:
        """Backtest-hjelper. Canonical backtest-navn er simulate_as_of()."""
        recommendation = self._next.recommend(recommendation_date)
        recommended = recommendation.get("workout_type")

        next_activity = self._next_running_activity(recommendation_date)
        actual_type = None
        actual_load = None
        session_quality = None
        if next_activity is not None:
            classification = self._classifier.classify_activity(
                next_activity,
                end_date=next_activity.start_time.date() if next_activity.start_time else recommendation_date,
            )
            actual_type = classification.get("session_type")
            actual_load = next_activity.training_stress_score or next_activity.epoc
            session_quality = self._quality.evaluate(next_activity).get("quality_score")

        adherence = self._adherence(recommended, actual_type)
        short_term = self._short_term_response(recommendation_date, session_quality)
        medium_term = self._medium_term_response(recommendation_date)

        return {
            "recommendation_date": recommendation_date.isoformat(),
            "recommended": recommended,
            "actual": actual_type,
            "adherence": adherence,
            "actual_load": float(actual_load) if actual_load is not None else None,
            "short_term_response": short_term,
            "medium_term_response": medium_term,
            "outcome": self._outcome_label(adherence, short_term, medium_term),
            "counterfactual_uncertainty": (
                "Cannot infer whether the recommendation was optimal when actual session differs — "
                "alternative outcomes are unobserved."
            ),
            "recommendation_confidence": recommendation.get("confidence"),
            "limitations": [
                "observational_not_causal",
                "adherence_independent_of_outcome_quality",
                "backtest_not_prospective",
            ],
        }

    def evaluate_recorded_recommendation(self, record_id: int) -> Dict[str, Any]:
        """Prospective: bruk lagret anbefaling — regenerer ikke dagens modell."""
        record = self._ledger.get_recommendation(record_id)
        if record is None:
            return {"status": "not_found", "record_id": record_id, "evaluation_kind": "prospective"}
        as_of = date.fromisoformat(record["as_of_date"])
        recommended = record["recommended_workout_type"]
        next_activity = self._next_running_activity(as_of)
        actual_type = None
        actual_load = None
        session_quality = None
        if next_activity is not None:
            classification = self._classifier.classify_activity(
                next_activity,
                end_date=next_activity.start_time.date() if next_activity.start_time else as_of,
            )
            actual_type = classification.get("session_type")
            actual_load = next_activity.training_stress_score or next_activity.epoc
            session_quality = self._quality.evaluate(next_activity).get("quality_score")
        adherence = self._adherence(recommended, actual_type)
        short_term = self._short_term_response(as_of, session_quality)
        medium_term = self._medium_term_response(as_of)
        return {
            "evaluation_kind": "prospective",
            "record_id": record_id,
            "recorded_model_version": record["model_version"],
            "recorded_config_hash": record["config_hash"],
            "recommendation_date": record["as_of_date"],
            "recommended": recommended,
            "actual": actual_type,
            "adherence": adherence,
            "actual_load": float(actual_load) if actual_load is not None else None,
            "short_term_response": short_term,
            "medium_term_response": medium_term,
            "outcome": self._outcome_label(adherence, short_term, medium_term),
            "did_not_regenerate_model": True,
            "counterfactual_uncertainty": (
                "Cannot infer whether the recommendation was optimal when actual session differs — "
                "alternative outcomes are unobserved."
            ),
            "recommendation_confidence": record.get("recommendation_confidence"),
            "limitations": [
                "observational_not_causal",
                "adherence_independent_of_outcome_quality",
                "uses_recorded_recommendation_not_current_code",
            ],
        }

    def evaluate_period(
        self,
        *,
        start_date: date,
        end_date: date,
        step_days: int = 7,
    ) -> Dict[str, Any]:
        rows: List[Dict[str, Any]] = []
        current = start_date
        while current <= end_date:
            rows.append(self.evaluate_as_of(current))
            current += timedelta(days=step_days)

        adherence_rate = None
        adhered = [r for r in rows if r.get("adherence") is not None]
        if adhered:
            adherence_rate = round(
                sum(1 for r in adhered if r["adherence"]) / len(adhered),
                2,
            )

        return {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "step_days": step_days,
            "evaluation_kind": "backtest",
            "evaluations": rows,
            "summary": {
                "count": len(rows),
                "adherence_rate": adherence_rate,
                "note": "Backtest only. Adherence ≠ recommendation correctness.",
            },
        }

    def evaluate_recorded_period(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> Dict[str, Any]:
        from ..database.models.coaching_v5 import RecommendationRecord

        rows = (
            self.db.query(RecommendationRecord)
            .filter(
                RecommendationRecord.as_of_date >= start_date,
                RecommendationRecord.as_of_date <= end_date,
            )
            .order_by(RecommendationRecord.as_of_date.asc())
            .all()
        )
        evaluations = [self.evaluate_recorded_recommendation(row.id) for row in rows]
        return {
            "evaluation_kind": "prospective",
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "evaluations": evaluations,
            "summary": {"count": len(evaluations), "note": "Uses recorded recommendations only."},
        }

    def _next_running_activity(self, after: date) -> Optional[Activity]:
        end = after + timedelta(days=3)
        activities = (
            self.db.query(Activity)
            .options(joinedload(Activity.activity_type))
            .filter(
                and_(
                    func.date(Activity.start_time) > after,
                    func.date(Activity.start_time) <= end,
                )
            )
            .order_by(Activity.start_time.asc())
            .all()
        )
        for activity in activities:
            if is_running_activity(activity):
                return activity
        return None

    @staticmethod
    def _adherence(recommended: Optional[str], actual: Optional[str]) -> Optional[bool]:
        if recommended is None or actual is None:
            return None
        if recommended == "rest":
            return False  # there was a session when rest recommended
        compatible = WORKOUT_TO_SESSION.get(recommended, set())
        return actual in compatible or actual == recommended

    def _short_term_response(
        self,
        day: date,
        session_quality: Optional[float],
    ) -> Dict[str, Any]:
        hrv_before = self._mean_hrv(day - timedelta(days=2), day)
        hrv_after = self._mean_hrv(day + timedelta(days=1), day + timedelta(days=3))
        rhr_before = self._mean_rhr(day - timedelta(days=2), day)
        rhr_after = self._mean_rhr(day + timedelta(days=1), day + timedelta(days=3))

        hrv_delta = None
        if hrv_before and hrv_after:
            hrv_delta = round(hrv_after - hrv_before, 1)
        rhr_delta = None
        if rhr_before and rhr_after:
            rhr_delta = round(rhr_after - rhr_before, 1)

        return {
            "hrv_delta": hrv_delta,
            "rhr_delta": rhr_delta,
            "session_quality": session_quality,
        }

    def _medium_term_response(self, day: date) -> Dict[str, Any]:
        ctl_now = self._ppap.get_ctl(day)
        ctl_later = self._ppap.get_ctl(day + timedelta(days=14))
        fitness_change = None
        if ctl_now is not None and ctl_later is not None:
            fitness_change = round(float(ctl_later) - float(ctl_now), 2)

        from .adaptive_threshold_service import AdaptiveThresholdService

        lt_now = AdaptiveThresholdService(self.db, self.storage).estimate_lt1(end_date=day)
        lt_later = AdaptiveThresholdService(self.db, self.storage).estimate_lt1(
            end_date=day + timedelta(days=28)
        )
        threshold_change = None
        if lt_now.get("lt1_pace_sec_km") and lt_later.get("lt1_pace_sec_km"):
            # Lower pace sec/km is faster
            threshold_change = round(
                float(lt_now["lt1_pace_sec_km"]) - float(lt_later["lt1_pace_sec_km"]),
                1,
            )

        return {
            "fitness_change": fitness_change,
            "threshold_change": threshold_change,
            "note": "Positive threshold_change means faster LT1 pace (sec/km decreased).",
        }

    def _mean_hrv(self, start: date, end: date) -> Optional[float]:
        rows = (
            self.db.query(HRV.rmssd)
            .filter(
                and_(
                    HRV.measurement_date >= start,
                    HRV.measurement_date <= end,
                    HRV.rmssd.isnot(None),
                )
            )
            .all()
        )
        values = [float(r.rmssd) for r in rows]
        return sum(values) / len(values) if values else None

    def _mean_rhr(self, start: date, end: date) -> Optional[float]:
        rows = (
            self.db.query(RestingHeartRate.resting_heart_rate)
            .filter(
                and_(
                    RestingHeartRate.measurement_date >= start,
                    RestingHeartRate.measurement_date <= end,
                    RestingHeartRate.resting_heart_rate.isnot(None),
                )
            )
            .all()
        )
        values = [float(r.resting_heart_rate) for r in rows]
        return sum(values) / len(values) if values else None

    @staticmethod
    def _outcome_label(
        adherence: Optional[bool],
        short_term: Dict[str, Any],
        medium_term: Dict[str, Any],
    ) -> str:
        hrv_delta = short_term.get("hrv_delta")
        quality = short_term.get("session_quality")
        fitness = medium_term.get("fitness_change")
        positive_signals = 0
        negative_signals = 0
        if hrv_delta is not None:
            if hrv_delta >= 0:
                positive_signals += 1
            elif hrv_delta < -5:
                negative_signals += 1
        if quality is not None:
            if quality >= 70:
                positive_signals += 1
            elif quality < 50:
                negative_signals += 1
        if fitness is not None:
            if fitness > 0:
                positive_signals += 1
            elif fitness < -2:
                negative_signals += 1
        if positive_signals > negative_signals:
            return "favorable_response"
        if negative_signals > positive_signals:
            return "unfavorable_response"
        return "inconclusive"
