from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..dependencies import get_db
from ..database.models.activity import Activity
from ..dependencies import get_data_storage
from ..storage import DataStorage
from ..services.performance_metrics_service import PerformanceMetricsService
from ..services.coaching_analysis_service import CoachingAnalysisService
from ..utils.activity_filters import apply_running_activity_filter

router = APIRouter()


def _coerce_query_default(value, default):
    if isinstance(value, type(default)):
        return value
    return default


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


@router.get("/coaching")
def get_coaching_analysis(
    days: int = Query(90, ge=14, le=365, description="Analyseperiode i dager"),
    recalculate: bool = Query(False, description="Beregn på nytt og lagre snapshot"),
    include_treadmill: bool = Query(
        False,
        description="Inkluder tredemølle og innendørs løping i intensitetsanalysen",
    ),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage),
):
    """Samlet coachinganalyse: fitness/fatigue, 80/20, terskler og HRV-readiness."""
    service = CoachingAnalysisService(db, storage)
    if not recalculate:
        snapshot = service.get_snapshot_payload()
        if (
            snapshot
            and snapshot.get("period", {}).get("days") == days
            and snapshot.get("period", {}).get("include_treadmill") == include_treadmill
        ):
            return snapshot
    return service.build_coaching_analysis(
        days=days,
        include_treadmill=include_treadmill,
        persist_snapshot=True,
    )


@router.get("/efficiency", response_model=AnalyticsListResponse)
def list_efficiency_trends(
    days: Optional[int] = Query(None, description="Begrens til siste N dager"),
    limit: int = Query(100, ge=1, le=1000, description="Maks antall aktiviteter"),
    include_treadmill: bool = Query(
        False,
        description="Inkluder tredemølle og innendørs løping i tillegg til utendørs løp",
    ),
    db: Session = Depends(get_db),
):
    """Trend/liste over lagrede Efficiency Factor-metrics per aktivitet."""
    if not isinstance(days, int):
        days = None
    query = apply_running_activity_filter(
        db.query(Activity).filter(Activity.avg_efficiency_factor.isnot(None)),
        include_treadmill=include_treadmill,
    )
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


_INSUFFICIENT_CRITICAL_SPEED = {
    "critical_speed_mps": None,
    "critical_pace_sec_per_km": None,
    "d_prime": None,
    "model_r2": None,
    "model_quality": "insufficient_data",
    "efforts": [],
}


@router.get("/critical-speed")
def get_critical_speed(
    recalculate: bool = Query(False, description="Beregn på nytt fra FIT-data"),
    include_treadmill: bool = Query(
        False,
        description="Inkluder tredemølle og innendørs løping i tillegg til utendørs løp",
    ),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage),
):
    service = PerformanceMetricsService(db, storage)
    if recalculate:
        payload = service.recalculate_performance_snapshots()["critical_speed"]
    else:
        payload = service.get_snapshot_payload("critical_speed")
    return service.resolve_critical_speed_payload(payload, include_treadmill=include_treadmill)


@router.get("/critical-speed/pace-by-year")
def get_critical_speed_pace_by_year(
    years: int = Query(3, ge=1, le=10),
    include_treadmill: bool = Query(
        False,
        description="Inkluder tredemølle og innendørs løping i tillegg til utendørs løp",
    ),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage),
):
    """Beste CS-varighets-pace per kalenderår, med utfylling fra samme økt som lengste effort."""
    service = PerformanceMetricsService(db, storage)
    return service.build_critical_speed_pace_by_year(years=years, include_treadmill=include_treadmill)


@router.get("/fatigue-resistance", response_model=AnalyticsListResponse)
def list_fatigue_resistance(
    days: Optional[int] = Query(None, description="Begrens til siste N dager"),
    limit: int = Query(100, ge=1, le=1000, description="Maks antall aktiviteter"),
    include_treadmill: bool = Query(
        False,
        description="Inkluder tredemølle og innendørs løping i tillegg til utendørs løp",
    ),
    db: Session = Depends(get_db),
):
    if not isinstance(days, int):
        days = None
    query = apply_running_activity_filter(
        db.query(Activity).filter(Activity.fatigue_resistance_score.isnot(None)),
        include_treadmill=include_treadmill,
    )
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


@router.get("/duration-curve/year-comparison")
def get_duration_curve_year_comparison(
    metric: str = Query("speed", pattern="^(speed|power)$"),
    years: int = Query(3, ge=1, le=10, description="Antall kalenderår tilbake inkl. inneværende"),
    include_treadmill: bool = Query(
        False,
        description="Inkluder tredemølle og innendørs løping i tillegg til utendørs løp",
    ),
    recalculate: bool = Query(False, description="Beregn på nytt fra FIT-data"),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage),
):
    """Beste duration curve per kalenderår for sammenligning (f.eks. siste 3 år)."""
    service = PerformanceMetricsService(db, storage)
    if recalculate:
        payload = service.recalculate_performance_snapshots()["duration_curve"]
    else:
        payload = service.get_snapshot_payload("duration_curve")

    snapshot_key = "by_year_with_treadmill" if include_treadmill else "by_year"
    by_year_snapshot = (payload or {}).get(snapshot_key, {})
    current_year = datetime.now(timezone.utc).year
    target_years = [current_year - offset for offset in range(years - 1, -1, -1)]

    series = []
    for year in target_years:
        year_key = str(year)
        year_data = by_year_snapshot.get(year_key)
        if year_data is None:
            year_data = service.build_duration_curve_for_calendar_year(
                year,
                include_treadmill=include_treadmill,
            )
        curves = year_data.get("curves", {})
        series.append(
            {
                "year": year,
                "points": curves.get(metric, []),
                "effort_count": year_data.get("effort_count", 0),
            }
        )

    return {
        "metric": metric,
        "years": series,
        "include_treadmill": include_treadmill,
        "calculated_at": (payload or {}).get("calculated_at"),
    }


@router.get("/duration-curve")
def get_duration_curve(
    metric: str = Query("speed", pattern="^(speed|power)$"),
    scope: str = Query("all_time", pattern="^(all_time|last_90_days|last_365_days)$"),
    include_treadmill: bool = Query(
        False,
        description="Inkluder tredemølle og innendørs løping i tillegg til utendørs løp",
    ),
    recalculate: bool = Query(False, description="Beregn på nytt fra FIT-data"),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage),
):
    metric = _coerce_query_default(metric, "speed")
    scope = _coerce_query_default(scope, "all_time")
    include_treadmill = _coerce_query_default(include_treadmill, False)
    recalculate = _coerce_query_default(recalculate, False)
    service = PerformanceMetricsService(db, storage)
    scope_days = {"all_time": None, "last_90_days": 90, "last_365_days": 365}
    if recalculate or include_treadmill:
        scoped = service.build_duration_curve(
            days=scope_days[scope],
            include_treadmill=include_treadmill,
        )
        calculated_at = datetime.now(timezone.utc).isoformat()
    else:
        payload = service.get_snapshot_payload("duration_curve")
        if payload is None:
            payload = {
                "all_time": {"curves": {"speed": [], "power": []}, "effort_count": 0},
                "last_90_days": {"curves": {"speed": [], "power": []}, "effort_count": 0},
                "last_365_days": {"curves": {"speed": [], "power": []}, "effort_count": 0},
                "by_year": {},
                "calculated_at": None,
            }
        scoped = payload.get(scope, {})
        calculated_at = payload.get("calculated_at")
    curves = scoped.get("curves", {})
    return {
        "metric": metric,
        "scope": scope,
        "points": curves.get(metric, []),
        "effort_count": scoped.get("effort_count", 0),
        "calculated_at": calculated_at,
        "include_treadmill": include_treadmill,
    }


@router.get("/decoupling", response_model=AnalyticsListResponse)
def list_decoupling_trends(
    days: Optional[int] = Query(None, description="Begrens til siste N dager"),
    limit: int = Query(100, ge=1, le=1000, description="Maks antall aktiviteter"),
    include_treadmill: bool = Query(
        False,
        description="Inkluder tredemølle og innendørs løping i tillegg til utendørs løp",
    ),
    db: Session = Depends(get_db),
):
    """Trend/liste over lagrede aerobic decoupling-metrics per aktivitet."""
    if not isinstance(days, int):
        days = None
    query = apply_running_activity_filter(
        db.query(Activity).filter(Activity.decoupling_percent.isnot(None)),
        include_treadmill=include_treadmill,
    )
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
