"""Today cockpit HTTP wrappers — composes CoachingOrchestrator only."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..dependencies import get_db, get_data_storage
from ..services.coaching_orchestrator import CoachingOrchestrator
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
