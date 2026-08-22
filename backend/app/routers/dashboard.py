"""Today cockpit HTTP wrappers — composes CoachingOrchestrator only."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..dependencies import get_db, get_data_storage
from ..database.models.coaching_v5 import RecommendationRecord
from ..database.models.activity import Activity
from ..services.coaching_orchestrator import CoachingOrchestrator
from ..services.comparable_session_service import ComparableSessionService
from ..services.decision_historical_support_service import DecisionHistoricalSupportService
from ..services.goal_context_service import GoalContextService
from ..services.mesocycle_planner import MesocyclePlanner
from ..services.plan_adaptation_service import PlanAdaptationService
from ..services.plan_stability import PlanStabilityService
from ..services.plan_vs_actual_service import PlanVsActualService
from ..services.ppap_metrics_service import PpapMetricsService
from ..services.recommendation_ledger_service import RecommendationLedgerService
from ..services.session_quality_service import SessionQualityService
from ..services.training_phase_service import TrainingPhaseService
from ..services.training_plan_store import TrainingPlanStore
from ..services.update_delta_service import UpdateDeltaService
from ..services.weekly_plan_service import WeeklyPlanService
from ..storage import DataStorage

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _format_athlete_state(
    athlete_state: Optional[Dict[str, Any]],
    summary: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    state = athlete_state or {}
    summary = summary or {}

    def _dim(key: str, label: str) -> Dict[str, Any]:
        raw = state.get(key) or {}
        summ = summary.get(key) or {}
        value = raw.get("value") if isinstance(raw, dict) else raw
        trend = raw.get("trend") if isinstance(raw, dict) else summ.get("trend")
        status = raw.get("status") if isinstance(raw, dict) else None
        return {
            "key": key,
            "label": label,
            "value": value,
            "trend": trend,
            "status": status,
            "summary": summ,
        }

    return {
        "readiness_label": _readiness_label(state, summary),
        "dimensions": [
            _dim("recovery", "Restitusjon"),
            _dim("fitness", "Form"),
            _dim("fatigue", "Utmattelse"),
        ],
        "durability": _dim("durability", "Holdbarhet"),
        "aerobic_efficiency": _dim("aerobic_efficiency", "Aerob effektivitet"),
        "raw": state,
    }


def _readiness_label(state: Dict[str, Any], summary: Dict[str, Any]) -> str:
    recovery = state.get("recovery") or summary.get("recovery") or {}
    fatigue = state.get("fatigue") or summary.get("fatigue") or {}
    rec_val = recovery.get("value") if isinstance(recovery, dict) else recovery
    fat_val = fatigue.get("value") if isinstance(fatigue, dict) else fatigue
    if rec_val is not None and rec_val >= 70 and (fat_val is None or fat_val <= 55):
        return "Klar for normal trening"
    if rec_val is not None and rec_val < 45:
        return "Prioriter restitusjon"
    if fat_val is not None and fat_val >= 65:
        return "Redusert kapasitet i dag"
    return "Tilpass intensitet etter dagsform"


def _key_trends_from_brief(brief: Dict[str, Any]) -> List[Dict[str, Any]]:
    trends: List[Dict[str, Any]] = []
    bundle = brief.get("context_adjusted_trends") or {}
    if isinstance(bundle, dict):
        for name, payload in list(bundle.items())[:6]:
            if not isinstance(payload, dict):
                continue
            trends.append(
                {
                    "metric": name,
                    "label": payload.get("label") or name,
                    "direction": payload.get("direction"),
                    "relative_change_pct": payload.get("relative_change_pct"),
                    "current": payload.get("current"),
                }
            )
    if trends:
        return trends

    summary = brief.get("athlete_state_summary") or {}
    for key, label in (("fitness", "Form"), ("recovery", "Restitusjon"), ("fatigue", "Utmattelse")):
        dim = summary.get(key) or {}
        if not isinstance(dim, dict):
            continue
        if dim.get("trend"):
            trends.append(
                {
                    "metric": key,
                    "label": label,
                    "direction": dim.get("trend"),
                    "relative_change_pct": None,
                    "current": dim.get("value"),
                }
            )
    return trends


def compose_today_payload(brief: Dict[str, Any]) -> Dict[str, Any]:
    if brief.get("status") != "ok":
        return brief

    rec = brief.get("recommendation") or {}
    plan = brief.get("plan") or {}
    prescription = brief.get("workout_prescription") or rec.get("workout_prescription")

    return {
        "as_of": brief.get("date"),
        "generated_at": brief.get("date"),
        "status": brief.get("status"),
        "persisted": bool(brief.get("persisted")),
        "current_recommendation_id": brief.get("current_recommendation_id"),
        "athlete_state": _format_athlete_state(
            brief.get("athlete_state"),
            brief.get("athlete_state_summary"),
        ),
        "recommendation": {
            "decision_status": rec.get("decision_status"),
            "workout_type": rec.get("workout_type"),
            "workout": {
                "type": rec.get("workout_type"),
                "duration_min": rec.get("duration_min"),
                "target_hr": rec.get("target_hr"),
                "target_pace": rec.get("target_pace"),
                "rationale": rec.get("rationale"),
            },
            "prescription": prescription,
            "safe_alternatives": rec.get("safe_alternatives"),
            "confidence": rec.get("decision_confidence"),
            "evidence_strength": rec.get("evidence_strength"),
            "data_quality": rec.get("data_quality"),
        },
        "decision_explanation": brief.get("decision_explanation"),
        "why": brief.get("why"),
        "weekly_plan": {
            "plan_id": plan.get("plan_id"),
            "version": plan.get("version"),
            "week_objective": plan.get("week_objective"),
            "sessions": plan.get("sessions") or [],
        },
        "goal": brief.get("goal"),
        "training_phase": brief.get("training_phase"),
        "key_trends": _key_trends_from_brief(brief),
        "freshness": brief.get("data_freshness"),
        "warnings": brief.get("warnings") or [],
        "system_status": brief.get("system_health"),
        "plan_adaptation": brief.get("plan_adaptation"),
        "plan_stability": brief.get("plan_stability"),
        "evidence": brief.get("evidence"),
    }


@router.get("/today")
def get_today_dashboard(
    target_date: Optional[date] = Query(None, description="Dato (YYYY-MM-DD), standard er i dag"),
    persist: bool = Query(
        False,
        description="Persist recommendation to ledger (default preview only)",
    ),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage),
) -> dict:
    """Single summary payload for the Today cockpit."""
    day = target_date or date.today()
    try:
        orchestrator = CoachingOrchestrator(db, storage)
        brief = orchestrator.training_decision_brief(
            day,
            persist=persist,
            detail="standard",
        )
        return compose_today_payload(brief)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _ledger_predecessor(db: Session, current_id: int) -> Optional[Dict[str, Any]]:
    row = (
        db.query(RecommendationRecord)
        .filter(RecommendationRecord.superseded_by_id == current_id)
        .order_by(RecommendationRecord.generated_at.desc())
        .first()
    )
    if row is None:
        return None
    return RecommendationLedgerService(db)._to_dict(row)


@router.get("/what-changed")
def get_what_changed(
    target_date: Optional[date] = Query(None),
    refresh: bool = Query(
        True,
        description="Refresh live coaching decision (persist) before comparing",
    ),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage),
) -> dict:
    """Compare previous vs current recommendation context after data refresh."""
    day = target_date or date.today()
    ledger = RecommendationLedgerService(db)
    before = ledger.get_latest_active_recommendation(as_of_date=day)

    if refresh:
        try:
            CoachingOrchestrator(db, storage).generate_live_decision(day, detail="standard")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    after = ledger.get_latest_active_recommendation(as_of_date=day)
    if before and after and before.get("id") == after.get("id"):
        compare_before = _ledger_predecessor(db, after["id"]) or before
    else:
        compare_before = before

    delta = UpdateDeltaService().compute(compare_before, after)
    return {
        "status": "ok",
        "as_of": day.isoformat(),
        **delta,
    }


@router.get("/post-sync-summary")
def get_post_sync_summary(
    activity_id: str = Query(..., description="Synced activity id"),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage),
) -> dict:
    """Interpretation-first summary for a newly synced session."""
    activity = (
        db.query(Activity)
        .filter(Activity.activity_id == str(activity_id))
        .first()
    )
    if activity is None:
        raise HTTPException(status_code=404, detail="activity_not_found")

    quality = SessionQualityService(db, storage).evaluate(activity)
    comparable = ComparableSessionService(db, storage).compare_to_personal_baseline(str(activity_id))

    quality_label = "unknown"
    score = quality.get("quality_score")
    if score is not None:
        if score >= 75:
            quality_label = "good"
        elif score >= 55:
            quality_label = "moderate"
        else:
            quality_label = "weak"

    percentile = comparable.get("percentile_vs_comparable")
    comparison_label = None
    if percentile is not None:
        if percentile >= 70:
            comparison_label = "above_average"
        elif percentile <= 30:
            comparison_label = "below_average"
        else:
            comparison_label = "typical"

    return {
        "status": "ok",
        "activity_id": str(activity_id),
        "activity_name": activity.activity_name,
        "session_type": quality.get("session_type"),
        "session_quality": {
            "label": quality_label,
            "score": score,
            "flags": quality.get("flags") or [],
            "confidence": quality.get("confidence"),
        },
        "comparable": {
            "count": comparable.get("comparable_count") or 0,
            "percentile": percentile,
            "comparison_label": comparison_label,
            "limitations": comparable.get("limitations") or [],
        },
        "interpretation": quality.get("interpretation"),
        "plan_effect": {
            "note": "Plan impact evaluated on next coaching refresh.",
        },
    }


@router.get("/recommendation-history")
def get_recommendation_history(
    limit: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    """Recent recommendation ledger entries for analytical review."""
    ledger = RecommendationLedgerService(db)
    rows = (
        db.query(RecommendationRecord)
        .filter(RecommendationRecord.is_shadow.is_(False))
        .order_by(RecommendationRecord.generated_at.desc(), RecommendationRecord.id.desc())
        .limit(limit)
        .all()
    )
    items = []
    for row in rows:
        rec = ledger._to_dict(row)
        items.append(
            {
                "id": rec.get("id"),
                "as_of_date": rec.get("as_of_date"),
                "generated_at": rec.get("generated_at"),
                "recommended": rec.get("recommended_workout_type"),
                "decision_status": rec.get("decision_status"),
                "is_active": rec.get("is_active"),
                "evidence_strength": rec.get("evidence_strength"),
                "decision_confidence": rec.get("decision_confidence"),
            }
        )
    return {"status": "ok", "items": items, "count": len(items)}


def _format_plan_sessions(sessions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    formatted: List[Dict[str, Any]] = []
    for session in sessions or []:
        formatted.append(
            {
                "day_offset": session.get("day_offset"),
                "type": session.get("type"),
                "duration_min": session.get("duration_min"),
                "purpose": session.get("purpose"),
                "prescription": session.get("prescription"),
            }
        )
    return formatted


def compose_plan_payload(
    *,
    day: date,
    weekly: Dict[str, Any],
    mesocycle: Dict[str, Any],
    adaptation: Dict[str, Any],
    goal: Dict[str, Any],
    phase: Dict[str, Any],
    version_history: List[Dict[str, Any]],
    vs_actual: Dict[str, Any],
    plan_stability: Dict[str, Any],
    source: str,
) -> Dict[str, Any]:
    return {
        "status": "ok",
        "as_of": day.isoformat(),
        "week_start": weekly.get("week_start") or day.isoformat(),
        "source": source,
        "goal": goal,
        "training_phase": phase,
        "weekly_plan": {
            "plan_id": weekly.get("plan_id"),
            "version": weekly.get("version"),
            "week_objective": weekly.get("week_objective"),
            "sessions": _format_plan_sessions(weekly.get("sessions") or []),
            "target_volume_min": weekly.get("target_volume_min"),
            "hard_sessions": weekly.get("hard_sessions"),
            "scores": weekly.get("scores"),
        },
        "mesocycle": {
            "start": mesocycle.get("start"),
            "weeks": mesocycle.get("weeks"),
            "selected_candidate": mesocycle.get("selected_candidate"),
            "mesocycle": mesocycle.get("mesocycle") or [],
            "goal": mesocycle.get("goal"),
            "source": mesocycle.get("source"),
            "evidence_strength": mesocycle.get("evidence_strength"),
            "note": mesocycle.get("note"),
        },
        "plan_adaptation": {
            "plan_status": adaptation.get("plan_status"),
            "changes": adaptation.get("changes") or [],
            "reason": adaptation.get("reason") or [],
            "confidence": adaptation.get("confidence"),
            "signals": adaptation.get("signals"),
            "note": adaptation.get("note"),
        },
        "plan_stability": plan_stability.get("status"),
        "plan_stability_detail": plan_stability,
        "version_history": version_history,
        "vs_actual": vs_actual,
    }


@router.get("/plan")
def get_plan_dashboard(
    target_date: Optional[date] = Query(None, description="Referansedato (YYYY-MM-DD)"),
    mesocycle_weeks: int = Query(5, ge=4, le=6),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage),
) -> dict:
    """Dedicated plan cockpit — week, mesocycle, adaptation and plan vs actual."""
    day = target_date or date.today()
    try:
        ppap = PpapMetricsService(db, storage)
        goal_svc = GoalContextService(db, storage, ppap)
        goal = goal_svc.build(day)
        phase = TrainingPhaseService(db, storage, ppap, goal=goal).determine(day, goal=goal)
        store = TrainingPlanStore(db)
        stored = store.get_active_plan(day)
        weekly_svc = WeeklyPlanService(db, storage, ppap, goal=goal)
        weekly = stored or weekly_svc.build(day, goal=goal, persist=False, commit=False)
        if stored:
            weekly.setdefault("week_start", stored.get("week_start"))
        else:
            weekly.setdefault("week_start", day.isoformat())

        adaptation = PlanAdaptationService(db, storage, ppap, goal=goal).assess(
            day,
            plan=weekly,
            goal=goal,
            persist=False,
            commit=False,
        )
        mesocycle = MesocyclePlanner(db, storage, ppap, goal=goal).plan(
            day,
            weeks=mesocycle_weeks,
            goal=goal,
            compare_candidates=False,
        )
        version_history: List[Dict[str, Any]] = []
        plan_id = weekly.get("plan_id")
        if plan_id:
            version_history = store.list_versions(plan_id, limit=8)

        week_start = date.fromisoformat(str(weekly.get("week_start") or day.isoformat()))
        vs_actual = PlanVsActualService(db, storage).compare(weekly, week_start=week_start)
        plan_stability = PlanStabilityService().from_history(db, as_of=day)

        return compose_plan_payload(
            day=day,
            weekly=weekly,
            mesocycle=mesocycle,
            adaptation=adaptation,
            goal=goal,
            phase=phase,
            version_history=version_history,
            vs_actual=vs_actual,
            plan_stability=plan_stability,
            source="stored" if stored else "live",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/decision-historical-support")
def get_decision_historical_support(
    target_date: Optional[date] = Query(None),
    workout_type: Optional[str] = Query(None, description="Override workout type"),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage),
) -> dict:
    """Historical support context for WhyThisWorkout level 3."""
    day = target_date or date.today()
    try:
        resolved_type = workout_type
        if not resolved_type:
            brief = CoachingOrchestrator(db, storage).training_decision_brief(
                day,
                persist=False,
                detail="concise",
            )
            rec = brief.get("recommendation") or {}
            resolved_type = rec.get("workout_type")
        return DecisionHistoricalSupportService(db, storage).build(
            workout_type=resolved_type,
            as_of_date=day,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/comparable-sessions")
def get_comparable_sessions(
    activity_id: str = Query(..., description="Garmin activity id"),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage),
) -> dict:
    """Interpretation-first comparable session analysis for activity drill-down."""
    try:
        payload = ComparableSessionService(db, storage).compare_to_personal_baseline(str(activity_id))
        if payload.get("status") == "not_found":
            raise HTTPException(status_code=404, detail="activity_not_found")
        return payload
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
