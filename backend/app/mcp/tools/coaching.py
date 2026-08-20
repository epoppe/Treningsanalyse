"""Coaching-relaterte MCP-verktøy — domenelogikk delegeres til services/."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ...services.coaching_decision_metrics_service import CoachingDecisionMetricsService
from ...services.coaching_backtest_service import CoachingBacktestService
from ...services.next_best_workout_service import NextBestWorkoutService
from ...services.ppap_metrics_service import PpapMetricsService
from ...services.recommendation_ledger_service import RecommendationLedgerService
from ...services.session_classifier_service import SessionClassifierService
from ...services.trend_analysis_service import TrendAnalysisService
from ...storage import DataStorage
from .common import parse_date, resolve_activity


def _should_persist(day: date, persist: Optional[bool]) -> bool:
    if persist is False:
        return False
    if persist is True:
        return True
    return day >= date.today()


def _record_live_recommendation(
    db: Session,
    recommendation: Dict[str, Any],
    *,
    day: date,
    persist: Optional[bool],
    athlete_state: Optional[Dict[str, Any]] = None,
    weekly_plan: Optional[Dict[str, Any]] = None,
    model_health: Optional[str] = None,
    calibration: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    ledger = RecommendationLedgerService(db)
    if not _should_persist(day, persist):
        return ledger.record_recommendation(
            recommendation,
            as_of_date=day,
            persist=False,
            athlete_state=athlete_state,
            weekly_plan=weekly_plan,
            model_health=model_health,
            calibration=calibration,
        )
    latest = ledger.get_latest_active_recommendation(as_of_date=day)
    if latest:
        return ledger.supersede_recommendation(
            latest["id"],
            recommendation,
            as_of_date=day,
            athlete_state=athlete_state,
            weekly_plan=weekly_plan,
            model_health=model_health,
            calibration=calibration,
        )["current"]
    return ledger.record_recommendation(
        recommendation,
        as_of_date=day,
        persist=True,
        athlete_state=athlete_state,
        weekly_plan=weekly_plan,
        model_health=model_health,
        calibration=calibration,
    )


def recommend_next_session(
    db: Session,
    storage: DataStorage,
    *,
    target_date: Optional[str] = None,
    include_treadmill: bool = False,
    persist: Optional[bool] = None,
) -> Dict[str, Any]:
    day = parse_date(target_date) if target_date else date.today()
    ppap = PpapMetricsService(db, storage)
    service = NextBestWorkoutService(db, storage, ppap)
    recommendation = service.recommend(day, include_treadmill=include_treadmill)
    recorded = _record_live_recommendation(db, recommendation, day=day, persist=persist)
    return {
        "status": "ok",
        "date": day.isoformat(),
        "current_recommendation_id": recorded.get("id") if recorded else None,
        "persisted": bool(recorded and recorded.get("persisted")),
        **recommendation,
    }


def classify_activity_session(
    db: Session,
    storage: DataStorage,
    *,
    activity_id: Optional[str] = None,
    include_treadmill: bool = False,
) -> Dict[str, Any]:
    activity = resolve_activity(db, activity_id)
    if activity is None:
        return {"status": "not_found", "activity_id": activity_id}
    classifier = SessionClassifierService(db, storage)
    classification = classifier.classify_activity(activity, include_treadmill=include_treadmill)
    return {
        "status": "ok",
        "activity_id": activity.activity_id,
        "activity_name": activity.activity_name,
        **classification,
    }


def longitudinal_trends(
    db: Session,
    storage: DataStorage,
    *,
    target_date: Optional[str] = None,
) -> Dict[str, Any]:
    day = parse_date(target_date) if target_date else date.today()
    service = TrendAnalysisService(db, storage)
    return {"status": "ok", **service.analyze_all(end_date=day)}


def coaching_decision_snapshot(
    db: Session,
    storage: DataStorage,
    *,
    target_date: Optional[str] = None,
) -> Dict[str, Any]:
    day = parse_date(target_date) if target_date else date.today()
    service = CoachingDecisionMetricsService(db, PpapMetricsService(db, storage))
    return service.build_coaching_snapshot(day)


def coaching_backtest_summary(
    db: Session,
    storage: DataStorage,
    *,
    start_date: str,
    end_date: str,
    step_days: int = 7,
) -> Dict[str, Any]:
    service = CoachingBacktestService(db, storage)
    result = service.evaluate_period(
        start_date=parse_date(start_date),
        end_date=parse_date(end_date),
        step_days=step_days,
    )
    return {"status": "ok", **result}


def training_decision_brief(
    db: Session,
    storage: DataStorage,
    *,
    target_date: Optional[str] = None,
    persist: Optional[bool] = None,
) -> Dict[str, Any]:
    """Kompakt executive package for AI-coaching — ett kall."""
    from ...database.models.coaching_v5 import RecommendationRecord
    from ...services.athlete_feedback_service import AthleteFeedbackService
    from ...services.athlete_state_service import AthleteStateService
    from ...services.coaching_model_health_service import CoachingModelHealthService
    from ...services.context_adjusted_trend_service import ContextAdjustedTrendService
    from ...services.load_variability_service import LoadVariabilityService
    from ...services.personalization_stability_service import PersonalizationStabilityService
    from ...services.plan_adaptation_service import PlanAdaptationService
    from ...services.projected_athlete_state_service import ProjectedAthleteStateService
    from ...services.training_availability_service import TrainingAvailabilityService
    from ...services.weekly_plan_service import WeeklyPlanService

    day = parse_date(target_date) if target_date else date.today()
    ppap = PpapMetricsService(db, storage)
    state = AthleteStateService(db, storage, ppap).build_state(day)
    decision = CoachingDecisionMetricsService(db, ppap)
    health = CoachingModelHealthService(db, storage).assess(day)
    next_session = NextBestWorkoutService(db, storage, ppap).recommend(
        day, model_health=health.get("status")
    )
    load_var = LoadVariabilityService(db, storage, ppap).analyze(day)
    trends = ContextAdjustedTrendService(db, storage).analyze_performance_bundle(end_date=day)

    live = _should_persist(day, persist)
    weekly = WeeklyPlanService(db, storage, ppap).build(day, persist=live, next_rec=next_session)
    adaptation = PlanAdaptationService(db, storage, ppap).assess(
        day, plan=weekly, persist=live
    )
    recorded = _record_live_recommendation(
        db,
        next_session,
        day=day,
        persist=persist,
        athlete_state=state,
        weekly_plan=weekly,
        model_health=health.get("status"),
    )
    availability = TrainingAvailabilityService(db).constraints_for_week(day)
    projected = ProjectedAthleteStateService(db, storage, ppap).project(
        day, day + timedelta(days=6), planned_sessions=weekly.get("sessions") or []
    )
    stability = PersonalizationStabilityService(db).assess(as_of_date=day)
    rec_count = db.query(RecommendationRecord).count()
    from ...database.models.coaching_v5 import RecommendationExecution

    exec_count = db.query(RecommendationExecution).count()
    recent_exec = (
        db.query(RecommendationExecution)
        .order_by(RecommendationExecution.linked_at.desc())
        .first()
    )
    recent_feedback = AthleteFeedbackService(db).recent(limit=1)

    main_changes = []
    for key in ("fitness", "recovery", "aerobic_efficiency", "durability"):
        dim = state.get(key) or {}
        if dim.get("trend") in {"improving", "declining"}:
            main_changes.append({"dimension": key, "trend": dim.get("trend"), "value": dim.get("value")})

    limiters = decision.get_limiting_factors(day)
    top = sorted(limiters.items(), key=lambda item: item[1], reverse=True)[:3]

    data_warnings = list(health.get("warnings") or [])
    data_warnings.extend(load_var.get("flags") or [])

    candidates = next_session.get("candidate_workouts") or []
    compact_candidates = [
        {
            "workout_type": c.get("workout_type"),
            "eligible": c.get("eligible"),
            "ranking_score": c.get("ranking_score"),
            "ineligible_reason": c.get("ineligible_reason"),
        }
        for c in candidates
        if c.get("eligible") or c.get("workout_type") == next_session.get("workout_type")
    ][:6]

    compact_availability = [
        {
            "date": c.get("date"),
            "available": c.get("available"),
            "max_duration_min": c.get("max_duration_min"),
            "avoid_hard": c.get("avoid_hard"),
        }
        for c in availability
        if not c.get("available") or c.get("max_duration_min") or c.get("avoid_hard")
    ][:7]

    return {
        "status": "ok",
        "date": day.isoformat(),
        "current_recommendation_id": recorded.get("id") if recorded else None,
        "athlete_state": state,
        "main_changes": main_changes,
        "top_limiters": [{"limiter": k, "score": v} for k, v in top],
        "recent_training": {
            "load_variability": load_var,
            "context_adjusted_trends": trends,
            "training_block": decision.get_training_block(day),
        },
        "goal": next_session.get("goal"),
        "training_phase": next_session.get("training_phase"),
        "race_capability": next_session.get("race_capability"),
        "recommended_next_session": {
            "workout_type": next_session.get("workout_type"),
            "duration_min": next_session.get("duration_min"),
            "target_hr": next_session.get("target_hr"),
            "target_pace": next_session.get("target_pace"),
            "rationale": next_session.get("rationale"),
        },
        "workout_prescription": next_session.get("workout_prescription"),
        "candidate_workouts": compact_candidates,
        "decision_status": next_session.get("decision_status"),
        "safe_alternatives": next_session.get("safe_alternatives"),
        "plan": {
            "plan_id": weekly.get("plan_id"),
            "version": weekly.get("version"),
            "week_objective": weekly.get("week_objective"),
            "sessions": [
                {"day_offset": s.get("day_offset"), "type": s.get("type"), "duration_min": s.get("duration_min")}
                for s in weekly.get("sessions") or []
            ],
        },
        "weekly_plan": {
            "week_objective": weekly.get("week_objective"),
            "sessions": [
                {"day_offset": s.get("day_offset"), "type": s.get("type"), "duration_min": s.get("duration_min")}
                for s in weekly.get("sessions") or []
            ],
            "target_volume_min": weekly.get("target_volume_min"),
            "hard_sessions": weekly.get("hard_sessions"),
        },
        "availability_constraints": compact_availability,
        "projected_week": {
            "state_type": projected.get("state_type"),
            "uncertainty": projected.get("uncertainty"),
            "simulation": weekly.get("simulation"),
        },
        "recent_execution": (
            {
                "execution_status": recent_exec.execution_status,
                "planned_type": recent_exec.planned_type,
                "actual_type": recent_exec.actual_type,
                "overall_adherence": recent_exec.overall_adherence,
            }
            if recent_exec
            else None
        ),
        "recent_feedback": recent_feedback[0] if recent_feedback else None,
        "personalization_stability": stability.get("status"),
        "prospective_learning": {
            "recorded_recommendations": rec_count,
            "evaluated_outcomes": exec_count,
        },
        "adaptation_rules": weekly.get("adaptation_rules"),
        "plan_adaptation": {
            "plan_status": adaptation.get("plan_status"),
            "changes": adaptation.get("changes"),
            "reason": adaptation.get("reason"),
            "previous_plan_id": adaptation.get("previous_plan_id"),
            "new_plan_id": adaptation.get("new_plan_id"),
        },
        "decision_trace": next_session.get("decision_trace", []),
        "evidence_strength": next_session.get("evidence_strength"),
        "recommendation_confidence": next_session.get("recommendation_confidence"),
        "confidence": next_session.get("recommendation_confidence") or next_session.get("confidence"),
        "data_warnings": data_warnings,
        "model_health": health.get("status"),
    }


def session_quality(
    db: Session,
    storage: DataStorage,
    *,
    activity_id: Optional[str] = None,
) -> Dict[str, Any]:
    from ...services.session_quality_service import SessionQualityService

    activity = resolve_activity(db, activity_id)
    if activity is None:
        return {"status": "not_found", "activity_id": activity_id}
    result = SessionQualityService(db, storage).evaluate(activity)
    return {"status": "ok", "activity_id": activity.activity_id, **result}


def comparable_sessions(
    db: Session,
    storage: DataStorage,
    *,
    activity_id: Optional[str] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    from ...services.comparable_session_service import ComparableSessionService

    activity = resolve_activity(db, activity_id)
    if activity is None:
        return {"status": "not_found", "activity_id": activity_id}
    return ComparableSessionService(db, storage).compare_to_personal_baseline(
        str(activity.activity_id)
    )


def coaching_evaluation_report(
    db: Session,
    storage: DataStorage,
    *,
    target_date: Optional[str] = None,
    lookback_days: int = 90,
) -> Dict[str, Any]:
    from ...services.coaching_evaluation_service import CoachingEvaluationService

    day = parse_date(target_date) if target_date else date.today()
    payload = CoachingEvaluationService(db, storage).build_payload(
        end_date=day,
        lookback_days=lookback_days,
    )
    return {"status": "ok", **payload}
