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
from .canonical_prospective_observation import CanonicalProspectiveObservationService
from .next_best_workout_service import NextBestWorkoutService
from .outcome_maturity import PENDING
from .ppap_metrics_service import PpapMetricsService
from .recommendation_ledger_service import RecommendationLedgerService
from .recommendation_utility_evaluator import RecommendationUtilityEvaluator
from .session_classifier_service import SessionClassifierService

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
        self._utility = RecommendationUtilityEvaluator(db, storage, self._ppap)
        self._ledger = RecommendationLedgerService(db)
        self._canonical = CanonicalProspectiveObservationService(db)

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
            session_quality = self._utility.session_quality_score(
                next_activity.activity_id,
                session_type=actual_type,
            )

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

    def evaluate_recorded_recommendation(
        self,
        record_id: int,
        *,
        today: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Prospective: bruk lagret anbefaling — regenerer ikke dagens modell.

        RecommendationExecution is authoritative. The 3-day running-activity
        search is only a labeled legacy fallback when no execution link exists.
        """
        today = today or date.today()
        record = self._ledger.get_recommendation(record_id)
        if record is None:
            return {"status": "not_found", "record_id": record_id, "evaluation_kind": "prospective"}
        observation = self._canonical.resolve_one(record_id, today=today)
        if observation is None or observation.get("is_shadow"):
            return {
                "status": "excluded",
                "record_id": record_id,
                "evaluation_kind": "prospective",
                "excluded_reason": (observation or {}).get("excluded_reason", "not_canonical"),
            }
        canonical_record = record
        if observation["recommendation_id"] != record_id:
            canonical_record = self._ledger.get_recommendation(observation["recommendation_id"]) or record
        as_of = date.fromisoformat(observation["as_of_date"])
        recommended = observation["recommended_workout_type"]
        activity = self._activity_for_observation(observation)
        actual_type = observation.get("actual_type")
        actual_load = observation.get("actual_load")
        session_quality = None
        # Classify only the already-linked activity. Never search for a different one
        # when an explicit execution already chose the activity.
        if activity is not None and observation.get("match_source") == "legacy_heuristic":
            classification = self._classifier.classify_activity(
                activity,
                end_date=activity.start_time.date() if activity.start_time else as_of,
            )
            classified = classification.get("session_type")
            if classified:
                actual_type = classified
            if actual_load is None:
                load = activity.training_stress_score or activity.epoc
                actual_load = float(load) if load is not None else None
        elif activity is not None and observation.get("match_source") == "explicit_execution" and actual_load is None:
            load = activity.training_stress_score or activity.epoc
            actual_load = float(load) if load is not None else None
        if activity is not None and observation.get("match_source") in {"legacy_heuristic", "explicit_execution"}:
            session_quality = self._utility.session_quality_score(
                observation.get("activity_id"),
                session_type=actual_type,
            )

        execution_pending = observation.get("execution_status") == "pending"
        adherence = None if execution_pending else self._adherence(recommended, actual_type)
        if execution_pending or observation["maturity_status"]["execution"] == PENDING:
            short_term = {
                "hrv_delta": None,
                "rhr_delta": None,
                "session_quality": None,
                "maturity_status": "pending",
            }
            medium_term = {"fitness_change": None, "threshold_change": None, "maturity_status": "pending"}
            outcome = "pending"
        else:
            short_term = self._short_term_response(as_of, session_quality, today=today)
            medium_term = self._medium_term_response(as_of, today=today)
            # Execution can close a day before HRV/RHR. That day is still pending
            # physiology, not an inconclusive response.
            if short_term.get("maturity_status") == PENDING:
                outcome = "pending"
            else:
                outcome = self._outcome_label(adherence, short_term, medium_term)
        return {
            "evaluation_kind": "prospective",
            "record_id": observation["recommendation_id"],
            "requested_record_id": record_id,
            "canonical": True,
            "supersede_chain_length": observation["supersede_chain_length"],
            "recorded_model_version": canonical_record["model_version"],
            "recorded_config_hash": canonical_record["config_hash"],
            "recommendation_date": observation["as_of_date"],
            "recommended": recommended,
            "actual": actual_type,
            "activity_id": observation.get("activity_id"),
            "adherence": adherence,
            "actual_load": float(actual_load) if actual_load is not None else None,
            "short_term_response": short_term,
            "medium_term_response": medium_term,
            "outcome": outcome,
            "observation_status": observation.get("observation_status"),
            "maturity_status": {
                **observation.get("maturity_status", {}),
                "short_term": short_term.get("maturity_status"),
                "medium_term": medium_term.get("maturity_status"),
            },
            "match_source": observation.get("match_source"),
            "match_confidence": observation.get("match_confidence"),
            "match_reason": observation.get("match_reason"),
            "evidence_weight": observation.get("evidence_weight"),
            "execution_id": observation.get("execution_id"),
            "execution_status": observation.get("execution_status"),
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
                "explicit_execution_overrides_heuristic_activity_match",
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
        observations = self._canonical.resolve(start=start_date, end=end_date)
        evaluations = [
            self.evaluate_recorded_recommendation(row["recommendation_id"]) for row in observations
        ]
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

    def _activity_for_observation(self, observation: Dict[str, Any]) -> Optional[Activity]:
        activity_id = observation.get("activity_id")
        if not activity_id:
            return None
        return (
            self.db.query(Activity)
            .options(joinedload(Activity.activity_type))
            .filter(Activity.activity_id == activity_id)
            .first()
        )

    def _short_term_response(
        self,
        day: date,
        session_quality: Optional[float],
        *,
        today: Optional[date] = None,
    ) -> Dict[str, Any]:
        today = today or date.today()
        from .outcome_maturity import SHORT_TERM_LAG_DAYS, short_term_maturity, window_closed

        if not window_closed(day, today, SHORT_TERM_LAG_DAYS):
            return {
                "hrv_delta": None,
                "rhr_delta": None,
                "session_quality": None,
                "maturity_status": "pending",
            }
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

        has_value = any(value is not None for value in (hrv_delta, rhr_delta, session_quality))
        return {
            "hrv_delta": hrv_delta,
            "rhr_delta": rhr_delta,
            "session_quality": session_quality,
            "maturity_status": short_term_maturity(day, today, has_value=has_value),
        }

    def _medium_term_response(self, day: date, *, today: Optional[date] = None) -> Dict[str, Any]:
        today = today or date.today()
        from .outcome_maturity import MEDIUM_TERM_LAG_DAYS, medium_term_maturity, window_closed

        if not window_closed(day, today, MEDIUM_TERM_LAG_DAYS):
            return {
                "fitness_change": None,
                "threshold_change": None,
                "maturity_status": "pending",
                "note": "Medium-term window is still open. Missing change is not a negative response.",
            }
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

        has_value = fitness_change is not None or threshold_change is not None
        return {
            "fitness_change": fitness_change,
            "threshold_change": threshold_change,
            "maturity_status": medium_term_maturity(day, today, has_value=has_value),
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
