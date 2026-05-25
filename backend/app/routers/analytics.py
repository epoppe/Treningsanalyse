from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..dependencies import get_db
from ..database.models.activity import Activity
from ..dependencies import get_data_storage
from ..storage import DataStorage
from ..services.performance_metrics_service import PerformanceMetricsService

router = APIRouter()


class EfficiencyTrendItem(BaseModel):
    activityId: str
    activityName: Optional[str] = None
    startTimeLocal: datetime
    avgEfficiencyFactor: Optional[float] = None
    medianEfficiencyFactor: Optional[float] = None
    steadyStateEfficiencyFactor: Optional[float] = None
    efficiencyDataQuality: Optional[float] = None
    distance: Optional[float] = None
    duration: Optional[float] = None


class DecouplingTrendItem(BaseModel):
    activityId: str
    activityName: Optional[str] = None
    startTimeLocal: datetime
    decouplingPercent: Optional[float] = None
    decouplingSuitabilityFlag: Optional[str] = None
    decouplingReasonIfUnsuitable: Optional[str] = None
    decouplingDataQualityScore: Optional[float] = None
    avgEfficiencyFactor: Optional[float] = None
    distance: Optional[float] = None
    duration: Optional[float] = None


class FatigueResistanceItem(BaseModel):
    activityId: str
    activityName: Optional[str] = None
    startTimeLocal: datetime
    fatigueResistanceScore: Optional[float] = None
    paceDropPct: Optional[float] = None
    hrDriftPct: Optional[float] = None
    cadenceDropPct: Optional[float] = None
    efDropPct: Optional[float] = None
    distance: Optional[float] = None
    duration: Optional[float] = None


class AnalyticsListResponse(BaseModel):
    activities: List[dict]
    count: int = Field(description="Antall aktiviteter returnert")


@router.get("/efficiency", response_model=AnalyticsListResponse)
def list_efficiency_trends(
    days: Optional[int] = Query(None, description="Begrens til siste N dager"),
    limit: int = Query(100, ge=1, le=1000, description="Maks antall aktiviteter"),
    db: Session = Depends(get_db),
):
    """Trend/liste over lagrede Efficiency Factor-metrics per aktivitet."""
    if not isinstance(days, int):
        days = None
    query = db.query(Activity).filter(Activity.avg_efficiency_factor.isnot(None))
    if days is not None:
        cutoff = datetime.utcnow() - timedelta(days=days)
        query = query.filter(Activity.start_time >= cutoff)
    activities = query.order_by(Activity.start_time.desc()).limit(limit).all()

    items = [
        EfficiencyTrendItem(
            activityId=act.activity_id,
            activityName=act.activity_name,
            startTimeLocal=act.start_time,
            avgEfficiencyFactor=act.avg_efficiency_factor,
            medianEfficiencyFactor=act.median_efficiency_factor,
            steadyStateEfficiencyFactor=act.steady_state_efficiency_factor,
            efficiencyDataQuality=act.efficiency_data_quality,
            distance=act.distance,
            duration=act.duration,
        ).model_dump(by_alias=False)
        for act in activities
    ]
    return {"activities": items, "count": len(items)}


@router.get("/critical-speed")
def get_critical_speed(
    recalculate: bool = Query(False, description="Beregn på nytt fra FIT-data"),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage),
):
    service = PerformanceMetricsService(db, storage)
    if recalculate:
        return service.recalculate_performance_snapshots()["critical_speed"]
    return service.get_snapshot_payload("critical_speed") or service.recalculate_performance_snapshots()["critical_speed"]


@router.get("/fatigue-resistance", response_model=AnalyticsListResponse)
def list_fatigue_resistance(
    days: Optional[int] = Query(None, description="Begrens til siste N dager"),
    limit: int = Query(100, ge=1, le=1000, description="Maks antall aktiviteter"),
    db: Session = Depends(get_db),
):
    if not isinstance(days, int):
        days = None
    query = db.query(Activity).filter(Activity.fatigue_resistance_score.isnot(None))
    if days is not None:
        cutoff = datetime.utcnow() - timedelta(days=days)
        query = query.filter(Activity.start_time >= cutoff)
    activities = query.order_by(Activity.start_time.desc()).limit(limit).all()
    items = [
        FatigueResistanceItem(
            activityId=act.activity_id,
            activityName=act.activity_name,
            startTimeLocal=act.start_time,
            fatigueResistanceScore=act.fatigue_resistance_score,
            paceDropPct=act.pace_drop_pct,
            hrDriftPct=act.hr_drift_pct,
            cadenceDropPct=act.cadence_drop_pct,
            efDropPct=act.ef_drop_pct,
            distance=act.distance,
            duration=act.duration,
        ).model_dump(by_alias=False)
        for act in activities
    ]
    return {"activities": items, "count": len(items)}


@router.get("/duration-curve")
def get_duration_curve(
    metric: str = Query("speed", pattern="^(speed|power)$"),
    scope: str = Query("all_time", pattern="^(all_time|last_90_days|last_365_days)$"),
    recalculate: bool = Query(False, description="Beregn på nytt fra FIT-data"),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage),
):
    service = PerformanceMetricsService(db, storage)
    payload = (
        service.recalculate_performance_snapshots()["duration_curve"]
        if recalculate
        else service.get_snapshot_payload("duration_curve")
    )
    if payload is None:
        payload = service.recalculate_performance_snapshots()["duration_curve"]
    scoped = payload.get(scope, {})
    curves = scoped.get("curves", {})
    return {
        "metric": metric,
        "scope": scope,
        "points": curves.get(metric, []),
        "effort_count": scoped.get("effort_count", 0),
        "calculated_at": payload.get("calculated_at"),
    }


@router.get("/decoupling", response_model=AnalyticsListResponse)
def list_decoupling_trends(
    days: Optional[int] = Query(None, description="Begrens til siste N dager"),
    limit: int = Query(100, ge=1, le=1000, description="Maks antall aktiviteter"),
    db: Session = Depends(get_db),
):
    """Trend/liste over lagrede aerobic decoupling-metrics per aktivitet."""
    if not isinstance(days, int):
        days = None
    query = db.query(Activity).filter(Activity.decoupling_percent.isnot(None))
    if days is not None:
        cutoff = datetime.utcnow() - timedelta(days=days)
        query = query.filter(Activity.start_time >= cutoff)
    activities = query.order_by(Activity.start_time.desc()).limit(limit).all()

    items = [
        DecouplingTrendItem(
            activityId=act.activity_id,
            activityName=act.activity_name,
            startTimeLocal=act.start_time,
            decouplingPercent=act.decoupling_percent,
            decouplingSuitabilityFlag=act.decoupling_suitability_flag,
            decouplingReasonIfUnsuitable=act.decoupling_reason_if_unsuitable,
            decouplingDataQualityScore=act.decoupling_data_quality_score,
            avgEfficiencyFactor=act.avg_efficiency_factor,
            distance=act.distance,
            duration=act.duration,
        ).model_dump(by_alias=False)
        for act in activities
    ]
    return {"activities": items, "count": len(items)}
