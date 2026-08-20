"""Canonical coaching workflow. Owns transactions; no physiological logic here."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..schemas.coaching import DetailLevel, coerce_enum
from ..storage import DataStorage
from .athlete_state_service import AthleteStateService
from .calibration_snapshot_service import CalibrationSnapshotService
from .coaching_model_health_service import CoachingModelHealthService
from .coaching_model_registry import CoachingModelRegistry
from .coaching_request_cache import cache_key, coaching_request_cache, get_or_set
from .coaching_tx import coaching_transaction
from .context_adjusted_trend_service import ContextAdjustedTrendService
from .load_variability_service import LoadVariabilityService
from .next_best_workout_service import NextBestWorkoutService
from .personalization_stability_service import PersonalizationStabilityService
from .plan_adaptation_service import PlanAdaptationService
from .ppap_metrics_service import PpapMetricsService
from .projected_athlete_state_service import ProjectedAthleteStateService
from .recommendation_ledger_service import RecommendationLedgerService
from .shadow_recommendation_service import ShadowRecommendationService
from .training_availability_service import TrainingAvailabilityService
from .weekly_plan_service import WeeklyPlanService


class CoachingOrchestrator:
    def __init__(
        self,
        db: Session,
        storage: Optional[DataStorage] = None,
        goal: Optional[Dict[str, Any]] = None,
    ):
        self.db = db
        self.storage = storage
        self.goal = goal
        self._ppap = PpapMetricsService(db, storage)

    def preview_decision(
        self,
        day: Optional[date] = None,
        *,
        include_treadmill: bool = False,
        goal: Optional[Dict[str, Any]] = None,
        detail: str = "concise",
    ) -> Dict[str, Any]:
        """Never persist recommendation/plan/calibration."""
        return self._build(
            day or date.today(),
            include_treadmill=include_treadmill,
            goal=goal or self.goal,
            persist=False,
            detail=detail,
        )

    def generate_live_decision(
        self,
        day: Optional[date] = None,
        *,
        include_treadmill: bool = False,
        goal: Optional[Dict[str, Any]] = None,
        detail: str = "concise",
        update_calibration: bool = False,
        run_shadow: bool = True,
    ) -> Dict[str, Any]:
        """Atomic live decision: recommendation + plan (+ optional calibration)."""
        day = day or date.today()
        with coaching_request_cache():
            with coaching_transaction(self.db):
                return self._build(
                    day,
                    include_treadmill=include_treadmill,
                    goal=goal or self.goal,
                    persist=True,
                    detail=detail,
                    update_calibration=update_calibration,
                    run_shadow=run_shadow,
                    commit=False,
                )

    def recommend_next_session(
        self,
        day: Optional[date] = None,
        *,
        include_treadmill: bool = False,
        persist: Optional[bool] = None,
        goal: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        day = day or date.today()
        should_persist = persist if persist is not None else day >= date.today()
        if should_persist:
            brief = self.generate_live_decision(
                day,
                include_treadmill=include_treadmill,
                goal=goal,
                detail="concise",
                run_shadow=False,
            )
        else:
            brief = self.preview_decision(
                day,
                include_treadmill=include_treadmill,
                goal=goal,
                detail="standard",
            )
        rec = brief.get("recommendation") or {}
        return {
            "status": "ok",
            "date": day.isoformat(),
            "current_recommendation_id": brief.get("current_recommendation_id"),
            "persisted": bool(brief.get("persisted")),
            **rec,
        }

    def training_decision_brief(
        self,
        day: Optional[date] = None,
        *,
        persist: Optional[bool] = None,
        detail: str = "concise",
        goal: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        day = day or date.today()
        should_persist = persist if persist is not None else day >= date.today()
        if should_persist:
            return self.generate_live_decision(day, goal=goal, detail=detail)
        return self.preview_decision(day, goal=goal, detail=detail)

    def _build(
        self,
        day: date,
        *,
        include_treadmill: bool,
        goal: Optional[Dict[str, Any]],
        persist: bool,
        detail: str,
        update_calibration: bool = False,
        run_shadow: bool = False,
        commit: bool = True,
    ) -> Dict[str, Any]:
        detail_level = coerce_enum(DetailLevel, detail, DetailLevel.CONCISE)
        key = cache_key(as_of_date=day, include_treadmill=include_treadmill, goal=goal)

        health = get_or_set(
            "model_health",
            key,
            lambda: CoachingModelHealthService(self.db, self.storage).assess(day),
        )
        state = get_or_set(
            "athlete_state",
            key,
            lambda: AthleteStateService(self.db, self.storage, self._ppap).build_state(day),
        )
        next_svc = NextBestWorkoutService(self.db, self.storage, self._ppap, goal=goal)
        recommendation = next_svc.recommend(
            day,
            include_treadmill=include_treadmill,
            goal=goal,
            model_health=health.get("status"),
        )
        # Separate uncertainty semantics
        data_quality = self._data_quality(state, health, recommendation)
        evidence_strength = float(recommendation.get("evidence_strength") or 0.0)
        decision_confidence = float(
            recommendation.get("decision_confidence")
            or recommendation.get("recommendation_confidence")
            or recommendation.get("confidence")
            or 0.0
        )
        recommendation = {
            **recommendation,
            "data_quality": data_quality,
            "evidence_strength": evidence_strength,
            "decision_confidence": decision_confidence,
            # compatibility aliases
            "recommendation_confidence": decision_confidence,
            "confidence": decision_confidence,
        }

        if persist and update_calibration:
            CalibrationSnapshotService(self.db).update_from_calibration(as_of_date=day, commit=commit)

        weekly = WeeklyPlanService(self.db, self.storage, self._ppap, goal=goal).build(
            day,
            goal=goal,
            include_treadmill=include_treadmill,
            persist=persist,
            next_rec=recommendation,
            commit=commit,
        )
        adaptation = PlanAdaptationService(self.db, self.storage, self._ppap, goal=goal).assess(
            day,
            plan=weekly,
            persist=persist,
            commit=commit,
        )

        ledger = RecommendationLedgerService(self.db)
        recorded = None
        if persist:
            latest = ledger.get_latest_active_recommendation(as_of_date=day)
            if latest:
                recorded = ledger.supersede_recommendation(
                    latest["id"],
                    recommendation,
                    as_of_date=day,
                    athlete_state=state,
                    weekly_plan=weekly,
                    model_health=health.get("status"),
                    commit=commit,
                )["current"]
            else:
                recorded = ledger.record_recommendation(
                    recommendation,
                    as_of_date=day,
                    persist=True,
                    athlete_state=state,
                    weekly_plan=weekly,
                    model_health=health.get("status"),
                    data_quality={"score": data_quality},
                    commit=commit,
                )
        else:
            recorded = ledger.record_recommendation(
                recommendation,
                as_of_date=day,
                persist=False,
                athlete_state=state,
                weekly_plan=weekly,
                model_health=health.get("status"),
                data_quality={"score": data_quality},
                commit=False,
            )

        shadow = None
        if persist and run_shadow:
            shadow = ShadowRecommendationService(self.db, self.storage).record_shadow(
                day=day,
                production=recommendation,
                production_recommendation_id=recorded.get("id") if recorded else None,
                commit=commit,
            )

        availability = TrainingAvailabilityService(self.db).constraints_for_week(day)
        projected = ProjectedAthleteStateService(self.db, self.storage, self._ppap).project(
            day, day + timedelta(days=6), planned_sessions=weekly.get("sessions") or []
        )
        stability = PersonalizationStabilityService(self.db).assess(as_of_date=day)
        registry = CoachingModelRegistry(self.db).get_active("ranker")

        load_var = None
        trends = None
        if detail_level in {DetailLevel.STANDARD, DetailLevel.DIAGNOSTIC}:
            load_var = LoadVariabilityService(self.db, self.storage, self._ppap).analyze(day)
            trends = ContextAdjustedTrendService(self.db, self.storage).analyze_performance_bundle(
                end_date=day
            )

        from ..database.models.coaching_v5 import RecommendationExecution, RecommendationRecord
        from .athlete_feedback_service import AthleteFeedbackService

        rec_count = self.db.query(RecommendationRecord).count()
        exec_count = self.db.query(RecommendationExecution).count()
        recent_exec = (
            self.db.query(RecommendationExecution)
            .order_by(RecommendationExecution.linked_at.desc())
            .first()
        )
        recent_feedback = AthleteFeedbackService(self.db).recent(limit=1)

        brief = {
            "status": "ok",
            "date": day.isoformat(),
            "persisted": bool(recorded and recorded.get("persisted")),
            "current_recommendation_id": recorded.get("id") if recorded else None,
            "athlete_state_summary": self._state_summary(state),
            "goal": recommendation.get("goal"),
            "training_phase": recommendation.get("training_phase"),
            "recommendation": {
                "workout_type": recommendation.get("workout_type"),
                "duration_min": recommendation.get("duration_min"),
                "target_hr": recommendation.get("target_hr"),
                "target_pace": recommendation.get("target_pace"),
                "rationale": recommendation.get("rationale"),
                "decision_status": recommendation.get("decision_status"),
                "safe_alternatives": recommendation.get("safe_alternatives"),
                "data_quality": data_quality,
                "evidence_strength": evidence_strength,
                "decision_confidence": decision_confidence,
                "recommendation_confidence": decision_confidence,
            },
            "workout_prescription": recommendation.get("workout_prescription"),
            "plan": {
                "plan_id": weekly.get("plan_id"),
                "version": weekly.get("version"),
                "week_objective": weekly.get("week_objective"),
                "sessions": [
                    {
                        "day_offset": s.get("day_offset"),
                        "type": s.get("type"),
                        "duration_min": s.get("duration_min"),
                    }
                    for s in weekly.get("sessions") or []
                ],
            },
            "key_evidence": (recommendation.get("decision_trace") or [])[:5],
            "warnings": list(health.get("warnings") or []),
            "model_provenance": (recorded or {}).get("provenance"),
            "active_model": registry,
            "model_health": health.get("status"),
            "personalization_stability": stability.get("status"),
            "availability_constraints": [
                {
                    "date": c.get("date"),
                    "available": c.get("available"),
                    "max_duration_min": c.get("max_duration_min"),
                    "avoid_hard": c.get("avoid_hard"),
                }
                for c in availability
                if not c.get("available") or c.get("max_duration_min") or c.get("avoid_hard")
            ][:7],
            "projected_week": {
                "state_type": projected.get("state_type"),
                "uncertainty": projected.get("uncertainty"),
                "simulation": weekly.get("simulation"),
            },
            "plan_adaptation": {
                "plan_status": adaptation.get("plan_status"),
                "changes": adaptation.get("changes"),
                "reason": adaptation.get("reason"),
            },
            "prospective_learning": {
                "recorded_recommendations": rec_count,
                "evaluated_outcomes": exec_count,
            },
            "shadow": shadow,
            "detail": detail_level.value,
        }

        if detail_level != DetailLevel.CONCISE:
            brief["athlete_state"] = state
            brief["candidate_workouts"] = recommendation.get("candidate_workouts")
            brief["decision_trace"] = recommendation.get("decision_trace")
            brief["recent_execution"] = (
                {
                    "execution_status": recent_exec.execution_status,
                    "planned_type": recent_exec.planned_type,
                    "actual_type": recent_exec.actual_type,
                    "overall_adherence": recent_exec.overall_adherence,
                }
                if recent_exec
                else None
            )
            brief["recent_feedback"] = recent_feedback[0] if recent_feedback else None
            brief["load_variability"] = load_var
            brief["context_adjusted_trends"] = trends
        if detail_level == DetailLevel.DIAGNOSTIC:
            brief["weekly_plan_full"] = weekly
            brief["adaptation_full"] = adaptation
            brief["health_checks"] = health.get("checks")
        return brief

    @staticmethod
    def _state_summary(state: Dict[str, Any]) -> Dict[str, Any]:
        out = {}
        for key in ("fitness", "recovery", "fatigue"):
            dim = state.get(key) or {}
            out[key] = {"value": dim.get("value"), "trend": dim.get("trend")}
        return out

    @staticmethod
    def _data_quality(state: Dict[str, Any], health: Dict[str, Any], recommendation: Dict[str, Any]) -> float:
        signals = [
            (state.get("recovery") or {}).get("value") is not None,
            recommendation.get("context_summary", {}).get("tsb") is not None
            or (recommendation.get("context_summary") or {}).get("readiness") is not None,
            health.get("checks", {}).get("hrv_delta_present"),
            health.get("checks", {}).get("ctl_present"),
        ]
        present = sum(1 for s in signals if s)
        score = present / max(len(signals), 1)
        if health.get("status") == "insufficient_data":
            score = min(score, 0.35)
        elif health.get("status") == "degraded":
            score = min(score, 0.65)
        return round(score, 2)
