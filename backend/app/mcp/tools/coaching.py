"""Coaching-relaterte MCP-verktøy — domenelogikk delegeres til services/orchestrator."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ...services.coaching_backtest_service import CoachingBacktestService
from ...services.coaching_decision_metrics_service import CoachingDecisionMetricsService
from ...services.coaching_orchestrator import CoachingOrchestrator
from ...services.next_best_workout_service import NextBestWorkoutService
from ...services.ppap_metrics_service import PpapMetricsService
from ...services.session_classifier_service import SessionClassifierService
from ...services.trend_analysis_service import TrendAnalysisService
from ...storage import DataStorage
from .common import parse_date, resolve_activity


def recommend_next_session(
    db: Session,
    storage: DataStorage,
    *,
    target_date: Optional[str] = None,
    include_treadmill: bool = False,
    persist: Optional[bool] = None,
) -> Dict[str, Any]:
    day = parse_date(target_date) if target_date else date.today()
    return CoachingOrchestrator(db, storage).recommend_next_session(
        day,
        include_treadmill=include_treadmill,
        persist=persist,
    )


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
    detail: str = "concise",
) -> Dict[str, Any]:
    """Canonical brief via CoachingOrchestrator. Default detail=concise."""
    day = parse_date(target_date) if target_date else date.today()
    return CoachingOrchestrator(db, storage).training_decision_brief(
        day,
        persist=persist,
        detail=detail,
    )


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
