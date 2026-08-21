"""Coaching dashboard summary API — wraps existing orchestrator/services.

Does not change coaching algorithms. Frontend-facing payloads only.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..dependencies import get_db, get_data_storage
from ..services.athlete_concept_drift_service import AthleteConceptDriftService
from ..services.coaching_health_service import CoachingHealthService
from ..services.coaching_integrity_service import CoachingIntegrityService
from ..services.coaching_orchestrator import CoachingOrchestrator
from ..services.coaching_reason_codes import REASON_DOCS
from ..services.monthly_coaching_review_service import generate_monthly_coaching_review
from ..services.prospective_evidence_report_service import ProspectiveEvidenceReportService
from ..services.ppap_metrics_service import PpapMetricsService
from ..storage import DataStorage

router = APIRouter(prefix="/api/coaching", tags=["Coaching Dashboard"])


def _day(value: Optional[date]) -> date:
    return value or date.today()


@router.get("/today")
def get_today_dashboard(
    target_date: Optional[date] = Query(None, description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage),
) -> Dict[str, Any]:
    """One coherent payload for the Today cockpit (preview — does not persist)."""
    day = _day(target_date)
    try:
        orch = CoachingOrchestrator(db, storage)
        brief = orch.preview_decision(day, detail="standard")
        health = CoachingHealthService(db, PpapMetricsService(db, storage)).report(day)
        return {
            "date": day.isoformat(),
            "brief": brief,
            "system_attention": health.get("status") in {"attention_required", "critical"},
            "system_status": health.get("status"),
            "system_issues": health.get("issues") or [],
            "data_freshness": (health.get("checks") or {}).get("data_freshness") or {},
            "reason_docs": REASON_DOCS,
            "persisted": False,
            "note": "Preview payload — no recommendation/plan writes.",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _phase_label(training_phase: Any) -> Optional[str]:
    """Presentation-friendly phase string; orchestrator may return dict or str."""
    if training_phase is None:
        return None
    if isinstance(training_phase, str):
        return training_phase
    if isinstance(training_phase, dict):
        return (
            training_phase.get("phase")
            or training_phase.get("training_block")
            or training_phase.get("backwards_compatible_block")
        )
    return str(training_phase)


@router.get("/plan")
def get_plan_summary(
    target_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage),
) -> Dict[str, Any]:
    day = _day(target_date)
    try:
        brief = CoachingOrchestrator(db, storage).preview_decision(day, detail="standard")
        training_phase = brief.get("training_phase")
        return {
            "date": day.isoformat(),
            "plan": brief.get("plan"),
            "plan_stability": brief.get("plan_stability"),
            "plan_stability_detail": brief.get("plan_stability_detail"),
            "plan_adaptation": brief.get("plan_adaptation"),
            "goal": brief.get("goal"),
            "training_phase": _phase_label(training_phase),
            "training_phase_detail": training_phase
            if isinstance(training_phase, dict)
            else None,
            "projected_week": brief.get("projected_week"),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/progress-summary")
def get_progress_summary(
    target_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage),
) -> Dict[str, Any]:
    day = _day(target_date)
    try:
        ppap = PpapMetricsService(db, storage)
        brief = CoachingOrchestrator(db, storage).preview_decision(day, detail="concise")
        state = brief.get("athlete_state_summary") or {}
        return {
            "date": day.isoformat(),
            "athlete_state_summary": state,
            "ctl": ppap.get_ctl(day),
            "atl": ppap.get_atl(day),
            "tsb": ppap.get_tsb(day),
            "hrv_delta_pct": ppap.get_hrv_delta_pct(day),
            "rhr_delta_bpm": ppap.get_rhr_delta_bpm(day),
            "drill_down": {
                "vo2max": "/vo2max",
                "load": "/training-stress",
                "status": "/training-status",
                "analytics": "/analytics",
                "economy": "/ukesanalyse",
            },
            "note": "Summary only — specialist pages remain for charts.",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/insights-summary")
def get_insights_summary(
    target_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage),
) -> Dict[str, Any]:
    day = _day(target_date)
    try:
        drift = AthleteConceptDriftService(db, PpapMetricsService(db, storage)).assess(day)
        prospective = ProspectiveEvidenceReportService(db).report(end=day, window_days=90)
        return {
            "date": day.isoformat(),
            "concept_drift": {
                "overall": drift.get("overall"),
                "relationships": drift.get("relationships"),
                "note": drift.get("note"),
            },
            "prospective": {
                "recommendations": prospective.get("recommendations"),
                "execution": prospective.get("execution"),
                "outcomes": prospective.get("outcomes"),
                "evidence_sufficiency": prospective.get("evidence_sufficiency"),
            },
            "drill_down": {
                "hrv": "/hrv",
                "sleep": "/sovn",
                "stress": "/stress",
                "body_battery": "/body-battery",
                "relationships": "/sammenhenger",
            },
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/system-health")
def get_system_health(
    target_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage),
) -> Dict[str, Any]:
    day = _day(target_date)
    try:
        health = CoachingHealthService(db, PpapMetricsService(db, storage)).report(day)
        integrity = CoachingIntegrityService(db).check()
        return {
            "date": day.isoformat(),
            "health": health,
            "integrity": integrity,
            "sync_page": "/synkronisering",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/monthly-review")
def get_monthly_review(
    target_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    day = _day(target_date)
    try:
        return generate_monthly_coaching_review(db, end=day)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
