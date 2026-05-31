from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..config import settings
from ..database.session import get_db
from ..services.mcp_derived_metrics_service import McpDerivedMetricsService
from ..storage import DataStorage

router = APIRouter(prefix="/api/v1/readiness", tags=["Readiness v1"])


@router.get("/latest")
def get_readiness_latest(
    target_date: Optional[date] = Query(None, description="Dato (YYYY-MM-DD), standard er i dag"),
    db: Session = Depends(get_db),
) -> dict:
    """PPAP readiness snapshot: kompositter + CTL/ATL/TSB."""
    try:
        day = target_date or date.today()
        storage = DataStorage(settings.DATA_DIR)
        service = McpDerivedMetricsService(db, storage)
        payload = service.get_readiness_composites(day)
        return {
            "fitness_score": payload.get("fitness_score"),
            "fatigue_score": payload.get("fatigue_score"),
            "readiness_score": payload.get("readiness_score"),
            "recovery_score": payload.get("recovery_score"),
            "injury_risk_score": payload.get("injury_risk_score"),
            "performance_score": payload.get("performance_score"),
            "overtraining_score": payload.get("overtraining_score"),
            "fitness_ctl": payload.get("fitness_ctl"),
            "fitness_atl": payload.get("fitness_atl"),
            "fitness_tsb": payload.get("fitness_tsb"),
            "date": payload.get("date"),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
