from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterator, List, Optional

import pandas as pd
from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String
from sqlalchemy.orm import Session, selectinload

from ..config import settings
from ..database.models import BodyBattery, DailySummary, HRV, MonthlySummary, RestingHeartRate, Sleep, Stress, WeeklySummary, YearlySummary
from ..database.models.activity import (
    Activity,
    ActivityLap,
    ActivityRouteFingerprint,
    ActivityRouteMatch,
    AnalyticsSnapshot,
    GarminPerformanceMetric,
)
from ..database.models.lactate_threshold_history import LactateThresholdHistory
from ..database.session import SessionLocal
from ..services.coaching_analysis_service import CoachingAnalysisService
from ..services.mcp_derived_metrics_service import DERIVED_METRIC_CATALOG, McpDerivedMetricsService
from ..services.ppap_metrics_service import PpapMetricsService
from ..services.route_analysis_service import RouteAnalysisService
from ..storage import DataStorage
from ..utils.activity_filters import is_running_activity


METRIC_CATALOG: Dict[str, Dict[str, Any]] = {
    "activity.distance_m": {"model": Activity, "date_field": "start_time", "column": "distance", "category": "activity", "unit": "m"},
    "activity.duration_s": {"model": Activity, "date_field": "start_time", "column": "duration", "category": "activity", "unit": "s"},
    "activity.pace_sec_per_km": {"model": Activity, "date_field": "start_time", "column": None, "category": "activity", "unit": "s/km", "derived": "activity_pace"},
    "activity.average_heart_rate": {"model": Activity, "date_field": "start_time", "column": "average_heart_rate", "category": "activity", "unit": "bpm"},
    "activity.max_heart_rate": {"model": Activity, "date_field": "start_time", "column": "max_heart_rate", "category": "activity", "unit": "bpm"},
    "activity.average_speed_mps": {"model": Activity, "date_field": "start_time", "column": "average_speed", "category": "activity", "unit": "m/s"},
    "activity.grade_adjusted_speed_mps": {"model": Activity, "date_field": "start_time", "column": "avg_grade_adjusted_speed", "category": "activity", "unit": "m/s"},
    "activity.training_stress_score": {"model": Activity, "date_field": "start_time", "column": "training_stress_score", "category": "training_load", "unit": "score"},
    "activity.epoc": {"model": Activity, "date_field": "start_time", "column": "epoc", "category": "training_load", "unit": "score"},
    "activity.aerobic_training_effect": {"model": Activity, "date_field": "start_time", "column": "total_training_effect", "category": "training_effect", "unit": "score"},
    "activity.anaerobic_training_effect": {"model": Activity, "date_field": "start_time", "column": "total_anaerobic_training_effect", "category": "training_effect", "unit": "score"},
    "activity.vo2_max": {"model": Activity, "date_field": "start_time", "column": "vo2_max", "category": "performance", "unit": "ml/kg/min"},
    "activity.vo2_max_precise": {"model": Activity, "date_field": "start_time", "column": "vo2_max_precise", "category": "performance", "unit": "ml/kg/min"},
    "activity.decoupling_percent": {"model": Activity, "date_field": "start_time", "column": "decoupling_percent", "category": "aerobic_efficiency", "unit": "%"},
    "activity.hr_drift_pct": {"model": Activity, "date_field": "start_time", "column": "hr_drift_pct", "category": "aerobic_efficiency", "unit": "%"},
    "activity.fatigue_resistance_score": {"model": Activity, "date_field": "start_time", "column": "fatigue_resistance_score", "category": "fatigue", "unit": "score"},
    "activity.average_power": {"model": Activity, "date_field": "start_time", "column": "average_power", "category": "power", "unit": "W"},
    "activity.normalized_power": {"model": Activity, "date_field": "start_time", "column": "normalized_power", "category": "power", "unit": "W"},
    "activity.average_running_cadence": {"model": Activity, "date_field": "start_time", "column": "average_running_cadence", "category": "running_dynamics", "unit": "spm"},
    "activity.stride_length": {"model": Activity, "date_field": "start_time", "column": "stride_length", "category": "running_dynamics", "unit": "m"},
    "activity.vertical_oscillation": {"model": Activity, "date_field": "start_time", "column": "vertical_oscillation", "category": "running_dynamics", "unit": "cm"},
    "activity.vertical_ratio": {"model": Activity, "date_field": "start_time", "column": "vertical_ratio", "category": "running_dynamics", "unit": "%"},
    "activity.training_readiness_score": {"model": Activity, "date_field": "start_time", "column": "training_readiness_score", "category": "readiness", "unit": "score"},
    "activity.total_ascent": {"model": Activity, "date_field": "start_time", "column": "total_ascent", "category": "terrain", "unit": "m"},
    "activity.body_battery_delta": {"model": Activity, "date_field": "start_time", "column": "activity_body_battery_delta", "category": "recovery", "unit": "score"},
    "activity.begin_potential_stamina": {"model": Activity, "date_field": "start_time", "column": "begin_potential_stamina", "category": "stamina", "unit": "score"},
    "activity.end_potential_stamina": {"model": Activity, "date_field": "start_time", "column": "end_potential_stamina", "category": "stamina", "unit": "score"},
    "performance.vo2_max_precise": {"model": GarminPerformanceMetric, "date_field": "date", "column": "vo2_max_precise", "category": "performance", "unit": "ml/kg/min"},
    "performance.vo2_max": {"model": GarminPerformanceMetric, "date_field": "date", "column": "vo2_max", "category": "performance", "unit": "ml/kg/min"},
    "performance.training_status": {"model": GarminPerformanceMetric, "date_field": "date", "column": "training_status", "category": "training_status", "unit": "code"},
    "performance.acwr_percent": {"model": GarminPerformanceMetric, "date_field": "date", "column": "acwr_percent", "category": "training_load", "unit": "%"},
    "performance.daily_training_load_acute": {"model": GarminPerformanceMetric, "date_field": "date", "column": "daily_training_load_acute", "category": "training_load", "unit": "score"},
    "performance.daily_training_load_chronic": {"model": GarminPerformanceMetric, "date_field": "date", "column": "daily_training_load_chronic", "category": "training_load", "unit": "score"},
    "performance.load_aerobic_low": {"model": GarminPerformanceMetric, "date_field": "date", "column": "monthly_load_aerobic_low", "category": "load_balance", "unit": "score"},
    "performance.load_aerobic_high": {"model": GarminPerformanceMetric, "date_field": "date", "column": "monthly_load_aerobic_high", "category": "load_balance", "unit": "score"},
    "performance.load_anaerobic": {"model": GarminPerformanceMetric, "date_field": "date", "column": "monthly_load_anaerobic", "category": "load_balance", "unit": "score"},
    "performance.heat_acclimation": {"model": GarminPerformanceMetric, "date_field": "date", "column": "heat_acclimation_percentage", "category": "acclimation", "unit": "%"},
    "performance.altitude_acclimation": {"model": GarminPerformanceMetric, "date_field": "date", "column": "altitude_acclimation", "category": "acclimation", "unit": "m"},
    "performance.endurance_score": {"model": GarminPerformanceMetric, "date_field": "date", "column": "endurance_score", "category": "garmin_score", "unit": "score"},
    "performance.hill_score": {"model": GarminPerformanceMetric, "date_field": "date", "column": "hill_score", "category": "garmin_score", "unit": "score"},
    "health.hrv_rmssd": {"model": HRV, "date_field": "measurement_date", "column": "rmssd", "category": "hrv", "unit": "ms"},
    "health.sleep_score": {"model": Sleep, "date_field": "sleep_date", "column": "sleep_score", "category": "sleep", "unit": "score"},
    "health.sleep_overall_score": {"model": Sleep, "date_field": "sleep_date", "column": "overall_score", "category": "sleep", "unit": "score"},
    "health.sleep_duration_s": {"model": Sleep, "date_field": "sleep_date", "column": "total_sleep_time", "category": "sleep", "unit": "s"},
    "health.resting_heart_rate": {"model": RestingHeartRate, "date_field": "measurement_date", "column": "resting_heart_rate", "category": "recovery", "unit": "bpm"},
    "health.body_battery_max": {"model": BodyBattery, "date_field": "date", "column": "max_body_battery", "category": "recovery", "unit": "score"},
    "health.body_battery_min": {"model": BodyBattery, "date_field": "date", "column": "min_body_battery", "category": "recovery", "unit": "score"},
    "health.body_battery_net_charge": {"model": BodyBattery, "date_field": "date", "column": "net_charge", "category": "recovery", "unit": "score"},
    "health.stress_level": {"model": Stress, "date_field": "stress_date", "column": "stress_level", "category": "stress", "unit": "score"},
    "health.high_stress_time_s": {"model": Stress, "date_field": "stress_date", "column": "high_stress_time", "category": "stress", "unit": "s"},
}


SCALAR_METRIC_TYPES = (Integer, Float, Boolean, String)
EXCLUDED_METRIC_COLUMNS = {
    "id",
    "activity_id",
    "matched_activity_id",
    "activity_type_id",
    "lap_number",
    "route_group_key",
    "route_hash",
    "sampled_points",
    "raw_maxmet",
    "raw_training_load_balance",
    "raw_training_status",
    "raw_endurance_score",
    "raw_hill_score",
    "detailed_metrics",
    "detailed_sleep_data",
    "detailed_stress_data",
    "description",
    "activity_name",
    "device_name",
    "created_at",
    "updated_at",
    "calculated_at",
}
CATALOG_MODEL_SOURCES = [
    ("activity", Activity, "start_time", "activity"),
    ("performance", GarminPerformanceMetric, "date", "garmin_performance"),
    ("hrv", HRV, "measurement_date", "health_hrv"),
    ("sleep", Sleep, "sleep_date", "health_sleep"),
    ("resting_heart_rate", RestingHeartRate, "measurement_date", "health_recovery"),
    ("body_battery", BodyBattery, "date", "health_recovery"),
    ("stress", Stress, "stress_date", "health_stress"),
    ("lactate_threshold", LactateThresholdHistory, "observed_at", "threshold"),
    ("route_fingerprint", ActivityRouteFingerprint, "calculated_at", "route"),
    ("route_match", ActivityRouteMatch, "calculated_at", "route"),
    ("daily_summary", DailySummary, "date", "summary"),
    ("weekly_summary", WeeklySummary, "week_start_date", "summary"),
    ("monthly_summary", MonthlySummary, "month_start_date", "summary"),
    ("yearly_summary", YearlySummary, "year", "summary"),
]


def _augment_metric_catalog() -> None:
    for prefix, model, date_field, category in CATALOG_MODEL_SOURCES:
        columns = model.__table__.columns
        if date_field not in columns:
            continue
        for column in columns:
            if column.name == date_field or column.name in EXCLUDED_METRIC_COLUMNS:
                continue
            if isinstance(column.type, (Date, DateTime)):
                continue
            if not isinstance(column.type, SCALAR_METRIC_TYPES):
                continue
            key = f"{prefix}.{column.name}"
            METRIC_CATALOG.setdefault(
                key,
                {
                    "model": model,
                    "date_field": date_field,
                    "column": column.name,
                    "category": category,
                    "unit": _infer_metric_unit(column.name),
                    "auto_discovered": True,
                },
            )


def _infer_metric_unit(column_name: str) -> str:
    name = column_name.lower()
    if name in {"year", "week_number", "month"} or name.endswith("_count") or "count" in name:
        return "count"
    if "percent" in name or name.endswith("_pct") or "ratio" in name:
        return "%"
    if "heart_rate" in name or name.endswith("_hr") or "hr_" in name:
        return "bpm"
    if "speed" in name:
        return "m/s"
    if "pace" in name:
        return "s/km"
    if "distance" in name:
        return "m"
    if "duration" in name or "time" in name:
        return "s"
    if "power" in name:
        return "W"
    if "vo2" in name:
        return "ml/kg/min"
    if "altitude" in name or "elevation" in name or "ascent" in name or "descent" in name:
        return "m"
    if "temperature" in name:
        return "C"
    if "calorie" in name:
        return "kcal"
    if "score" in name or "status" in name or "effect" in name or "load" in name or "stamina" in name:
        return "score"
    return "value"


_augment_metric_catalog()


@contextmanager
def training_context() -> Iterator[tuple[Session, DataStorage]]:
    db = SessionLocal()
    storage = DataStorage(settings.DATA_DIR)
    try:
        yield db, storage
    finally:
        db.close()


def athlete_profile() -> Dict[str, Any]:
    with training_context() as (db, _storage):
        threshold = (
            db.query(LactateThresholdHistory)
            .order_by(LactateThresholdHistory.observed_at.desc())
            .first()
        )
        latest_perf = (
            db.query(GarminPerformanceMetric)
            .order_by(GarminPerformanceMetric.date.desc())
            .first()
        )
        latest_hrv = db.query(HRV).order_by(HRV.measurement_date.desc()).first()
        route_groups = (
            db.query(ActivityRouteFingerprint.route_group_key)
            .filter(ActivityRouteFingerprint.route_group_key.isnot(None))
            .distinct()
            .count()
        )
        activities = db.query(Activity).count()
        runs = [
            activity
            for activity in db.query(Activity).options(selectinload(Activity.activity_type)).all()
            if is_running_activity(activity)
        ]

        return {
            "athlete": {
                "measurement_system": "metric",
                "distance_unit": "km",
                "pace_unit": "min_per_km",
            },
            "data_inventory": {
                "activities": activities,
                "runs": len(runs),
                "route_groups": route_groups,
            },
            "latest_threshold": {
                "observed_at": threshold.observed_at.isoformat() if threshold else None,
                "lt2_heart_rate_bpm": threshold.lactate_threshold_heart_rate if threshold else None,
                "lt2_speed_mps": threshold.lactate_threshold_speed if threshold else None,
                "lt2_pace_sec_per_km": _pace_from_speed(threshold.lactate_threshold_speed) if threshold else None,
                "source": threshold.source if threshold else None,
            },
            "latest_garmin_performance": _garmin_performance_payload(latest_perf),
            "latest_hrv": {
                "date": latest_hrv.measurement_date.isoformat() if latest_hrv else None,
                "rmssd": latest_hrv.rmssd if latest_hrv else None,
                "status": latest_hrv.status if latest_hrv else None,
            },
            "stable_context": [
                "Use metric units and min/km pace.",
                "Prefer route-matched comparisons when evaluating repeated runs.",
                "Distinguish Garmin-derived metrics from calculated coaching heuristics.",
            ],
        }


def analyze_recent_training(days: int = 90, include_treadmill: bool = False) -> Dict[str, Any]:
    days = max(14, min(int(days), 365))
    with training_context() as (db, storage):
        service = CoachingAnalysisService(db, storage)
        return service.build_coaching_analysis(
            days=days,
            include_treadmill=include_treadmill,
            persist_snapshot=True,
        )


def training_readiness_check(target_date: Optional[str] = None) -> Dict[str, Any]:
    end_date = _parse_date(target_date) if target_date else date.today()
    with training_context() as (db, storage):
        service = CoachingAnalysisService(db, storage)
        analysis = service.build_coaching_analysis(days=90, end_date=end_date, persist_snapshot=True)
        banister = analysis["banister"]["summary"]
        hrv = analysis["hrv_guidance"]
        flags = analysis["diagnostics"]["flags"]
        if hrv["recommendation"] == "reduce_intensity_or_volume" or banister["status"] == "high_fatigue":
            recommendation = "easy_or_rest"
        elif hrv["recommendation"] == "keep_easy_or_moderate" or banister["status"] == "rapid_load_increase":
            recommendation = "easy_or_moderate"
        else:
            recommendation = "normal_training"

        return {
            "date": end_date.isoformat(),
            "recommendation": recommendation,
            "banister": banister,
            "hrv_guidance": hrv,
            "flags": flags,
        }


def list_recent_activities(
    limit: int = 10,
    activity_type: Optional[str] = None,
) -> Dict[str, Any]:
    limit = max(1, min(int(limit), 50))
    with training_context() as (db, _storage):
        query = db.query(Activity).options(selectinload(Activity.activity_type)).order_by(Activity.start_time.desc())
        activities = query.limit(300).all()
        if activity_type:
            activities = [
                activity
                for activity in activities
                if activity.activity_type and activity.activity_type.type_key == activity_type
            ]
        activities = activities[:limit]
        return {
            "activities": [_activity_summary(activity) for activity in activities],
            "count": len(activities),
        }


def activity_deep_dive(activity_id: Optional[str] = None) -> Dict[str, Any]:
    with training_context() as (db, storage):
        activity = _resolve_activity(db, activity_id)
        if activity is None:
            return {"status": "not_found", "activity_id": activity_id}
        splits = _kilometer_splits(activity, storage, db)
        route = db.query(ActivityRouteFingerprint).filter_by(activity_id=activity.activity_id).first()
        return {
            "status": "ok",
            "activity": _activity_summary(activity),
            "physiology": {
                "training_effect": activity.total_training_effect,
                "anaerobic_training_effect": activity.total_anaerobic_training_effect,
                "training_effect_label": activity.training_effect_label,
                "epoc": activity.epoc,
                "training_stress_score": activity.training_stress_score,
                "vo2_max": activity.vo2_max,
                "vo2_max_precise": activity.vo2_max_precise,
                "decoupling_percent": activity.decoupling_percent,
                "hr_drift_pct": activity.hr_drift_pct,
                "fatigue_resistance_score": activity.fatigue_resistance_score,
            },
            "route": {
                "route_group_key": route.route_group_key if route else None,
                "quality_score": route.quality_score if route else None,
                "route_distance_m": route.route_distance_m if route else None,
            },
            "kilometer_splits": splits,
        }


def route_comparison(activity_id: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
    limit = max(1, min(int(limit), 50))
    with training_context() as (db, storage):
        activity = _resolve_activity(db, activity_id, running_only=True)
        if activity is None:
            return {"status": "not_found", "activity_id": activity_id}
        service = RouteAnalysisService(storage)
        matches = service.get_activity_matches(activity.activity_id, db, same_route_only=True, limit=limit)
        enriched = []
        for match in matches:
            matched = db.query(Activity).filter_by(activity_id=str(match["activityId"])).first()
            if matched is None:
                continue
            enriched.append(
                {
                    **match,
                    "pace_sec_per_km": _activity_pace(matched),
                    "average_heart_rate": matched.average_heart_rate,
                    "training_effect": matched.total_training_effect,
                    "vo2_max": matched.vo2_max,
                }
            )
        return {
            "status": "ok",
            "activity": _activity_summary(activity),
            "matches": enriched,
            "count": len(enriched),
        }


def compare_recent_runs(limit: int = 5, same_route_as_latest: bool = False) -> Dict[str, Any]:
    limit = max(2, min(int(limit), 20))
    if same_route_as_latest:
        comparison = route_comparison(limit=limit)
        return {
            "mode": "same_route_as_latest",
            "latest_activity": comparison.get("activity"),
            "runs": comparison.get("matches", []),
        }

    with training_context() as (db, _storage):
        runs = [
            activity
            for activity in db.query(Activity).options(selectinload(Activity.activity_type)).order_by(Activity.start_time.desc()).limit(200).all()
            if is_running_activity(activity)
        ][:limit]
        return {
            "mode": "recent_runs",
            "runs": [_activity_summary(activity) for activity in runs],
            "count": len(runs),
        }


def coaching_snapshot() -> Dict[str, Any]:
    with training_context() as (db, _storage):
        snapshot = db.query(AnalyticsSnapshot).filter_by(metric_key="training_coaching").first()
        return snapshot.payload if snapshot and snapshot.payload else {"status": "missing"}



def duration_curve_snapshot(
    scope: str = "all_time",
    include_treadmill: bool = False,
) -> Dict[str, Any]:
    with training_context() as (db, storage):
        return PpapMetricsService(db, storage).duration_curve_snapshot(
            scope=scope,
            include_treadmill=include_treadmill,
        )


def duration_curve_year_comparison(
    years: int = 3,
    metric: str = "speed",
    include_treadmill: bool = False,
) -> Dict[str, Any]:
    years = max(1, min(int(years), 10))
    with training_context() as (db, storage):
        return PpapMetricsService(db, storage).duration_curve_year_comparison(
            years=years,
            metric=metric,
            include_treadmill=include_treadmill,
        )


def critical_speed_pace_by_year(
    years: int = 3,
    include_treadmill: bool = False,
) -> Dict[str, Any]:
    years = max(1, min(int(years), 10))
    with training_context() as (db, storage):
        return PpapMetricsService(db, storage).critical_speed_pace_by_year(
            years=years,
            include_treadmill=include_treadmill,
        )


def running_analysis_year_views(
    years: int = 3,
    metric: str = "speed",
    include_treadmill: bool = False,
) -> Dict[str, Any]:
    return {
        "duration_curve_year_comparison": duration_curve_year_comparison(
            years=years,
            metric=metric,
            include_treadmill=include_treadmill,
        ),
        "critical_speed_pace_by_year": critical_speed_pace_by_year(
            years=years,
            include_treadmill=include_treadmill,
        ),
    }


def metric_catalog() -> Dict[str, Any]:
    metrics = [
        {
            "key": key,
            "category": definition["category"],
            "unit": definition["unit"],
            "source": definition["model"].__tablename__,
            "scope": "stored",
        }
        for key, definition in sorted(METRIC_CATALOG.items())
    ]
    metrics.extend(
        [
            {
                "key": key,
                "category": definition["category"],
                "unit": definition["unit"],
                "scope": definition["scope"],
                "source": "derived",
                "heuristic": definition.get("heuristic", False),
            }
            for key, definition in sorted(DERIVED_METRIC_CATALOG.items())
        ]
    )
    categories = sorted({metric["category"] for metric in metrics})
    return {
        "schema_version": "ppap-3",
        "metrics": metrics,
        "count": len(metrics),
        "categories": categories,
        "note": "Use query_metric_timeseries with one of these whitelisted metric keys.",
    }


def query_metric_timeseries(
    metric_key: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 365,
) -> Dict[str, Any]:
    if metric_key in DERIVED_METRIC_CATALOG:
        limit = max(1, min(int(limit), 5000))
        with training_context() as (db, storage):
            service = McpDerivedMetricsService(db, storage)
            return service.query_timeseries(
                metric_key,
                start_date=_parse_date(start_date) if start_date else None,
                end_date=_parse_date(end_date) if end_date else None,
                limit=limit,
            )

    if metric_key not in METRIC_CATALOG:
        return {
            "status": "unknown_metric",
            "metric_key": metric_key,
            "available_metric_count": len(METRIC_CATALOG) + len(DERIVED_METRIC_CATALOG),
        }
    definition = METRIC_CATALOG[metric_key]
    model = definition["model"]
    date_field = getattr(model, definition["date_field"])
    limit = max(1, min(int(limit), 5000))
    start = _parse_date(start_date) if start_date else None
    end = _parse_date(end_date) if end_date else None

    with training_context() as (db, _storage):
        query = db.query(model)
        if model is Activity:
            query = query.options(selectinload(Activity.activity_type))
        if definition["date_field"] == "year":
            if start:
                query = query.filter(date_field >= start.year)
            if end:
                query = query.filter(date_field <= end.year)
        else:
            if start:
                query = query.filter(date_field >= start)
            if end:
                query = query.filter(date_field <= end)
        column = definition.get("column")
        if column:
            query = query.filter(getattr(model, column).isnot(None))
        rows = query.order_by(date_field.desc()).limit(limit).all()
        points = [_metric_point(row, definition) for row in reversed(rows)]
        points = [point for point in points if point["value"] is not None]
        return {
            "status": "ok",
            "metric_key": metric_key,
            "category": definition["category"],
            "unit": definition["unit"],
            "points": points,
            "count": len(points),
        }


def _resolve_activity(
    db: Session,
    activity_id: Optional[str],
    *,
    running_only: bool = False,
) -> Optional[Activity]:
    query = db.query(Activity).options(selectinload(Activity.activity_type))
    if activity_id:
        activity = query.filter_by(activity_id=str(activity_id)).first()
        if activity is None:
            return None
        return activity if not running_only or is_running_activity(activity) else None

    activities = query.order_by(Activity.start_time.desc()).limit(200).all()
    if running_only:
        return next((activity for activity in activities if is_running_activity(activity)), None)
    return activities[0] if activities else None


def _metric_point(row: Any, definition: Dict[str, Any]) -> Dict[str, Any]:
    date_value = getattr(row, definition["date_field"])
    if isinstance(date_value, datetime):
        date_iso = date_value.date().isoformat()
        timestamp = date_value.isoformat()
    elif isinstance(date_value, int):
        date_iso = str(date_value)
        timestamp = None
    else:
        date_iso = date_value.isoformat() if date_value else None
        timestamp = None

    if definition.get("derived") == "activity_pace":
        value = _activity_pace(row)
    else:
        value = getattr(row, definition["column"])

    point = {
        "date": date_iso,
        "timestamp": timestamp,
        "value": round(float(value), 3) if isinstance(value, (int, float)) else value,
    }
    if isinstance(row, Activity):
        point.update(
            {
                "activity_id": row.activity_id,
                "activity_name": row.activity_name,
                "activity_type": row.activity_type.type_key if row.activity_type else None,
            }
        )
    return point


def _activity_summary(activity: Activity) -> Dict[str, Any]:
    return {
        "activity_id": activity.activity_id,
        "name": activity.activity_name,
        "start_time": activity.start_time.isoformat() if activity.start_time else None,
        "date_readable": _readable_date(activity.start_time),
        "day_of_week": activity.start_time.strftime("%A") if activity.start_time else None,
        "activity_type": activity.activity_type.type_key if activity.activity_type else None,
        "distance_m": activity.distance,
        "distance_km": round(activity.distance / 1000, 2) if activity.distance else None,
        "duration_s": activity.duration,
        "pace_sec_per_km": _activity_pace(activity),
        "average_heart_rate": activity.average_heart_rate,
        "max_heart_rate": activity.max_heart_rate,
        "average_speed_mps": activity.average_speed,
        "training_stress_score": activity.training_stress_score,
        "epoc": activity.epoc,
    }


def _garmin_performance_payload(row: Optional[GarminPerformanceMetric]) -> Dict[str, Any]:
    if row is None:
        return {}
    return {
        "date": row.date.isoformat() if row.date else None,
        "vo2_max": row.vo2_max,
        "vo2_max_precise": row.vo2_max_precise,
        "training_status": row.training_status,
        "training_status_feedback": row.training_status_feedback_phrase,
        "training_balance_feedback": row.training_balance_feedback_phrase,
        "acute_load": row.daily_training_load_acute,
        "chronic_load": row.daily_training_load_chronic,
        "acwr_percent": row.acwr_percent,
        "endurance_score": row.endurance_score,
        "hill_score": row.hill_score,
    }


def _kilometer_splits(activity: Activity, storage: DataStorage, db: Session) -> List[Dict[str, Any]]:
    detail_splits = _splits_from_details(activity, storage)
    if detail_splits:
        return detail_splits
    laps = (
        db.query(ActivityLap)
        .filter(ActivityLap.activity_id == activity.activity_id)
        .order_by(ActivityLap.lap_number.asc())
        .all()
    )
    return [
        {
            "split": lap.lap_number,
            "distance_m": lap.distance,
            "duration_s": lap.duration,
            "pace_sec_per_km": round(lap.duration / (lap.distance / 1000), 1)
            if lap.distance and lap.duration
            else None,
            "average_heart_rate": lap.average_heart_rate,
            "source": "lap",
        }
        for lap in laps
        if lap.distance and lap.distance >= 100
    ]


def _splits_from_details(activity: Activity, storage: DataStorage) -> List[Dict[str, Any]]:
    try:
        details = storage.get_activity_details(int(activity.activity_id))
    except Exception:
        return []
    if details is None or details.empty or "timestamp" not in details.columns:
        return []

    df = details.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    if "distance" in df.columns:
        df["distance_m"] = pd.to_numeric(df["distance"], errors="coerce")
    elif "speed" in df.columns:
        speed = pd.to_numeric(df["speed"], errors="coerce").fillna(0)
        elapsed = (df["timestamp"] - df["timestamp"].iloc[0]).dt.total_seconds()
        dt = elapsed.diff().fillna(0).clip(lower=0, upper=10)
        df["distance_m"] = (speed * dt).cumsum()
    else:
        return []
    if "heart_rate" in df.columns:
        df["heart_rate"] = pd.to_numeric(df["heart_rate"], errors="coerce")
    else:
        df["heart_rate"] = None
    df = df.dropna(subset=["timestamp", "distance_m"]).sort_values("distance_m")
    if len(df) < 2 or df["distance_m"].max() < 1000:
        return []

    splits = []
    previous_time = df["timestamp"].iloc[0]
    previous_distance = 0.0
    max_km = int(df["distance_m"].max() // 1000)
    for km in range(1, max_km + 1):
        target = km * 1000
        target_rows = df[df["distance_m"] >= target]
        if target_rows.empty:
            break
        row = target_rows.iloc[0]
        duration_s = (row["timestamp"] - previous_time).total_seconds()
        segment = df[(df["distance_m"] > previous_distance) & (df["distance_m"] <= target)]
        splits.append(
            {
                "split": km,
                "distance_m": 1000,
                "duration_s": round(duration_s, 1),
                "pace_sec_per_km": round(duration_s, 1),
                "average_heart_rate": round(float(segment["heart_rate"].mean()), 1)
                if "heart_rate" in segment and not segment["heart_rate"].isna().all()
                else None,
                "source": "details",
            }
        )
        previous_time = row["timestamp"]
        previous_distance = target
    return splits


def _activity_pace(activity: Activity) -> Optional[float]:
    if activity.distance and activity.duration and activity.distance > 0:
        return round(activity.duration / (activity.distance / 1000), 1)
    if activity.average_speed and activity.average_speed > 0:
        return _pace_from_speed(activity.average_speed)
    return None


def _pace_from_speed(speed_mps: Optional[float]) -> Optional[float]:
    if speed_mps and speed_mps > 0:
        return round(1000 / speed_mps, 1)
    return None


def _readable_date(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.strftime("%A, %Y-%m-%d %H:%M")


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()
