from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterator, List, Optional

import pandas as pd
from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Session, selectinload

from ..config import settings
from ..services.hrv_fetch import hrv_mcp_recovery_payload
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
from ..services.metric_source_audit import (
    activity_summary_not_ingested_reason,
    audit_model_column_sources,
    body_battery_not_ingested_reason,
    performance_not_ingested_reason,
    sleep_vital_empty_source_reason,
)
from .metric_glossary import build_metric_glossary, get_glossary_entry
from .metric_quality import build_metric_quality_report, format_metric_quality_markdown
from .speed_metric_format import (
    audit_user_facing_speed_units,
    enrich_activity_summary_speed_fields,
    enrich_athlete_threshold_payload,
    enrich_derived_metric_point,
    enrich_dict_pace_fields,
    enrich_stored_metric_point,
    infer_metric_unit_for_column,
    mcp_display_unit,
)
from ..utils.speed_pace import mps_to_pace_sec_per_km
from ..services.route_analysis_service import RouteAnalysisService
from ..storage import DataStorage
from ..utils.activity_filters import is_running_activity


NOT_INGESTED_METRICS: Dict[str, str] = {
    "activity.intensity_factor": "Intensity Factor beregnes ikke og lagres ikke i activities ennå.",
    "activity.recovery_time": (
        "Recovery time per aktivitet finnes sjelden i Garmin activity summary "
        "(recoveryTime/timeToRecover). Ikke i FIT eller lokale parquet-filer."
    ),
    "activity.begin_potential_stamina": (
        "Potential stamina krever Garmin activity summary (beginPotentialStamina). "
        "Ikke tilgjengelig i FIT/parquet; lokale rader mangler feltet fordi summary ikke returnerte verdier."
    ),
    "activity.end_potential_stamina": (
        "Potential stamina krever Garmin activity summary (endPotentialStamina). "
        "Ikke tilgjengelig i FIT/parquet; lokale rader mangler feltet fordi summary ikke returnerte verdier."
    ),
    "activity.min_available_stamina": (
        "Min available stamina krever Garmin activity summary (minAvailableStamina). "
        "Ikke tilgjengelig i FIT/parquet; lokale rader mangler feltet fordi summary ikke returnerte verdier."
    ),
    "health.body_battery_net_charge": (
        "Net charge krever charged/drained fra wellness-tidsserie. "
        "Eksisterende DB-rader har kun max/min; tidsserie ble ikke persistert ved sync."
    ),
    "body_battery.body_battery_charged": (
        "Charged/drained utledes fra body_battery_values_array ved sync, men tidsserien "
        "lagres ikke i DB. Eksisterende rader har kun max/min."
    ),
    "body_battery.body_battery_charged_start": (
        "Startverdier utledes fra wellness-tidsserie ved sync; tidsserie er ikke lagret i DB."
    ),
    "body_battery.body_battery_drained": (
        "Charged/drained utledes fra body_battery_values_array ved sync, men tidsserien "
        "lagres ikke i DB. Eksisterende rader har kun max/min."
    ),
    "body_battery.body_battery_drained_start": (
        "Startverdier utledes fra wellness-tidsserie ved sync; tidsserie er ikke lagret i DB."
    ),
    "body_battery.net_charge": (
        "Net charge krever charged/drained eller wellness-tidsserie. "
        "Eksisterende DB-rader har kun max/min uten persistert tidsserie."
    ),
    "performance.fitness_age": (
        "fitnessAge i lagret raw_maxmet er null fra Garmin for denne kontoen "
        "(generic.fitnessAge mangler verdi i alle synkede rader)."
    ),
    "performance.endurance_score": (
        "raw_endurance_score er null fra Garmin metrics-service for denne kontoen."
    ),
    "performance.endurance_classification": (
        "raw_endurance_score er null fra Garmin metrics-service for denne kontoen."
    ),
    "performance.hill_score": (
        "raw_hill_score er null fra Garmin metrics-service for denne kontoen."
    ),
    "performance.hill_endurance_score": (
        "raw_hill_score er null fra Garmin metrics-service for denne kontoen."
    ),
    "performance.hill_strength_score": (
        "raw_hill_score er null fra Garmin metrics-service for denne kontoen."
    ),
    "hrv.breathing_rate": "Kun et kjerneutvalg HRV-felt lagres i dagens sync.",
    "hrv.heart_rate": "Kun et kjerneutvalg HRV-felt lagres i dagens sync.",
    "hrv.measurement_duration": "Kun et kjerneutvalg HRV-felt lagres i dagens sync.",
    "hrv.measurement_quality": "Kun et kjerneutvalg HRV-felt lagres i dagens sync.",
    "hrv.pnn50": "Kun et kjerneutvalg HRV-felt lagres i dagens sync.",
    "hrv.stress_score": "Kun et kjerneutvalg HRV-felt lagres i dagens sync.",
    "resting_heart_rate.confidence_level": (
        "Garmin dailyHeartRate returnerer ikke confidenceLevel; feltet synkes ikke i dagens pipeline."
    ),
    "resting_heart_rate.measurement_quality": (
        "Garmin dailyHeartRate returnerer ikke measurementQuality; feltet synkes ikke i dagens pipeline."
    ),
    "stress.activity_stress_duration": "Kun stress_level og high_stress_time lagres i dagens sync.",
    "stress.data_quality": "Kun stress_level og high_stress_time lagres i dagens sync.",
}

UNSUPPORTED_METRICS: Dict[str, str] = {
    "running.power_30m": "30-min power er definert i ordboken, men ikke implementert i duration-curve-katalogen.",
    "running.power_30m_hist": "30-min power er definert i ordboken, men ikke implementert i duration-curve-katalogen.",
    "running.speed_30m": "30-min speed er definert i ordboken, men ikke implementert i duration-curve-katalogen.",
    "running.speed_30m_hist": "30-min speed er definert i ordboken, men ikke implementert i duration-curve-katalogen.",
}

DERIVED_EMPTY_SOURCE_DEPENDENCIES: Dict[str, tuple[Any, str]] = {
    "cardio.rhr_7d": (RestingHeartRate, "Resting heart rate-tabellen er tom."),
    "cardio.rhr_30d": (RestingHeartRate, "Resting heart rate-tabellen er tom."),
}

ACTIVITY_BODY_BATTERY_METRICS: Dict[str, str] = {
    "activity.body_battery_start": "body_battery_start",
    "activity.body_battery_delta": "activity_body_battery_delta",
    "activity.activity_body_battery_delta": "activity_body_battery_delta",
}

GRADE_ADJUSTED_PACE_METRIC = "activity.grade_adjusted_pace_sec_per_km"
GRADE_ADJUSTED_PACE_EMPTY_REASON = (
    "Grade Adjusted Pace mangler når verken Garmin (avgGradeAdjustedSpeed) "
    "eller FIT-beregning (fart+høyde, Minetti 2002) kan fylle feltet. "
    "Verdien lagres som m/s i activities.avg_grade_adjusted_speed og eksponeres som M:SS/km."
)

# Alias → kanonisk nøkkel (auto-oppdagede duplikater peker til health.* / eksplisitte nøkler)
METRIC_KEY_ALIASES: Dict[str, str] = {
    "hrv.rmssd": "health.hrv_rmssd",
    "sleep.sleep_score": "health.sleep_score",
    "sleep.overall_score": "health.sleep_overall_score",
    "sleep.total_sleep_time": "health.sleep_duration_s",
    "resting_heart_rate.resting_heart_rate": "health.resting_heart_rate",
    "body_battery.max_body_battery": "health.body_battery_max",
    "body_battery.min_body_battery": "health.body_battery_min",
    "body_battery.net_charge": "health.body_battery_net_charge",
    "stress.stress_level": "health.stress_level",
    "stress.high_stress_time": "health.high_stress_time_s",
    "activity.activity_body_battery_delta": "activity.body_battery_delta",
    "activity.grade_adjusted_speed_mps": "activity.grade_adjusted_pace_sec_per_km",
    "activity.avg_grade_adjusted_speed": "activity.grade_adjusted_pace_sec_per_km",
}


def _resolve_metric_key(metric_key: str) -> tuple[str, Optional[str]]:
    canonical = METRIC_KEY_ALIASES.get(metric_key, metric_key)
    alias_of = metric_key if canonical != metric_key else None
    return canonical, alias_of


def _metric_alias_index() -> Dict[str, List[str]]:
    index: Dict[str, List[str]] = {}
    for alias, canonical in METRIC_KEY_ALIASES.items():
        index.setdefault(canonical, []).append(alias)
    return index

METRIC_SEMANTIC_LINKS: List[Dict[str, Any]] = [
    {
        "topic": "Readiness",
        "primary": "readiness.total_score",
        "related": [
            "readiness.sleep_component",
            "readiness.hrv_component",
            "readiness.form_component",
            "activity.training_readiness_score",
            "readiness_score",
        ],
        "note": (
            "readiness.total_score er Garmin-modellen (TrainingReadinessService). "
            "readiness_score er intern coaching-heuristikk — ikke bytt om."
        ),
    },
    {
        "topic": "HRV",
        "primary": "health.hrv_rmssd",
        "related": [
            "cardio.hrv_7d",
            "cardio.hrv_30d",
            "recovery.hrv_baseline",
            "recovery.hrv_delta_pct",
        ],
        "note": "health.hrv_rmssd er rå nattverdi; cardio/recovery-* er rullerende eller delta.",
    },
    {
        "topic": "Body Battery",
        "primary": "health.body_battery_max",
        "related": [
            "activity.body_battery_start",
            "activity.activity_body_battery_delta",
            "activity.body_battery_delta",
        ],
        "note": (
            "activity.body_battery_delta og activity.activity_body_battery_delta peker på samme kolonne; "
            "start er estimert per aktivitet."
        ),
    },
    {
        "topic": "Belastning",
        "primary": "fitness.tsb",
        "related": ["fitness.ctl", "fitness.atl", "load.acwr", "fitness_score", "fatigue_score"],
        "note": "CTL/ATL/TSB fra lokal TSS; load.acwr fra Garmin der tilgjengelig.",
    },
]

METRIC_CATALOG: Dict[str, Dict[str, Any]] = {
    "activity.distance_m": {"model": Activity, "date_field": "start_time", "column": "distance", "category": "activity", "unit": "m"},
    "activity.duration_s": {"model": Activity, "date_field": "start_time", "column": "duration", "category": "activity", "unit": "s"},
    "activity.pace_sec_per_km": {"model": Activity, "date_field": "start_time", "column": None, "category": "activity", "unit": "M:SS/km", "derived": "activity_pace"},
    "activity.average_heart_rate": {"model": Activity, "date_field": "start_time", "column": "average_heart_rate", "category": "activity", "unit": "bpm"},
    "activity.max_heart_rate": {"model": Activity, "date_field": "start_time", "column": "max_heart_rate", "category": "activity", "unit": "bpm"},
    "activity.average_speed_mps": {"model": Activity, "date_field": "start_time", "column": "average_speed", "category": "activity", "unit": "km/h"},
    "activity.grade_adjusted_pace_sec_per_km": {
        "model": Activity,
        "date_field": "start_time",
        "column": "avg_grade_adjusted_speed",
        "category": "activity",
        "unit": "M:SS/km",
        "derived": "grade_adjusted_pace",
    },
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
    "activity.ground_contact_time": {
        "model": Activity,
        "date_field": "start_time",
        "column": "ground_contact_time",
        "category": "running_dynamics",
        "unit": "ms",
    },
    "activity.vertical_oscillation": {"model": Activity, "date_field": "start_time", "column": "vertical_oscillation", "category": "running_dynamics", "unit": "cm"},
    "activity.vertical_ratio": {"model": Activity, "date_field": "start_time", "column": "vertical_ratio", "category": "running_dynamics", "unit": "%"},
    "activity.training_readiness_score": {"model": Activity, "date_field": "start_time", "column": "training_readiness_score", "category": "readiness", "unit": "score"},
    "activity.total_ascent": {"model": Activity, "date_field": "start_time", "column": "total_ascent", "category": "terrain", "unit": "m"},
    "activity.body_battery_start": {"model": Activity, "date_field": "start_time", "column": "body_battery_start", "category": "recovery", "unit": "score"},
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
    "avg_grade_adjusted_speed",
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
    _refresh_metric_catalog_units()


def _refresh_metric_catalog_units() -> None:
    """Oppdater enheter for auto-oppdagede felt (inkl. eksisterende catalog-nøkler)."""
    for definition in METRIC_CATALOG.values():
        column = definition.get("column")
        if column and not definition.get("derived"):
            definition["unit"] = _infer_metric_unit(column)


def _infer_metric_unit(column_name: str) -> str:
    name = column_name.lower()
    if name in {"year", "week_number", "month"} or name.endswith("_count") or name == "count":
        return "count"
    if name.endswith("_trend"):
        return "%"
    if "percent" in name or name.endswith("_pct"):
        return "%"
    if name.endswith("_ratio") or name.endswith("_ratio_pct"):
        return "%"
    if name in {"ground_contact_time", "stance_time"} or name.endswith("contact_time"):
        return "ms"
    if "duration" in name:
        return "s"
    if "heart_rate" in name or name.endswith("_hr") or name.startswith("hr_"):
        return "bpm"
    speed_unit = infer_metric_unit_for_column(name)
    if speed_unit:
        return speed_unit
    if "pace" in name:
        return "M:SS/km"
    if "distance" in name:
        return "m"
    if "time" in name:
        return "s"
    if "power" in name:
        return "W"
    if "direction" in name:
        return "degrees"
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


def _model_table_counts(db: Session) -> Dict[Any, int]:
    models = {definition["model"] for definition in METRIC_CATALOG.values()}
    models.update(model for model, _reason in DERIVED_EMPTY_SOURCE_DEPENDENCIES.values())
    return {
        model: db.query(model).count()
        for model in models
    }


def _activity_body_battery_fill_stats(db: Session) -> Dict[str, int]:
    total = db.query(Activity).count()
    start_filled = db.query(Activity).filter(
        Activity.body_battery_start.isnot(None),
        Activity.body_battery_start >= 0,
    ).count()
    delta_filled = db.query(Activity).filter(Activity.activity_body_battery_delta.isnot(None)).count()
    return {"total": total, "start_filled": start_filled, "delta_filled": delta_filled}


def _grade_adjusted_pace_fill_stats(db: Session) -> Dict[str, int]:
    total = db.query(Activity).count()
    filled = db.query(Activity).filter(Activity.avg_grade_adjusted_speed.isnot(None)).count()
    return {"total": total, "filled": filled}


def _activity_column_fill_stats(db: Session, column: str) -> Dict[str, int]:
    return audit_model_column_sources(db, Activity, column)


def _stored_column_fill_availability(
    definition: Dict[str, Any],
    db: Session,
) -> Optional[Dict[str, str]]:
    column = definition.get("column")
    if not column or definition.get("derived"):
        return None
    stats = audit_model_column_sources(db, definition["model"], column)
    table = definition["model"].__tablename__
    if stats["filled"] == 0:
        return {
            "availability": "empty_source",
            "availability_reason": (
                f"Kolonne `{column}` i `{table}` har 0/{stats['total']} rader med verdi "
                "i denne databasen etter sync/backfill."
            ),
        }
    return {
        "availability": "supported",
        "availability_reason": (
            f"Data lagret for {stats['filled']}/{stats['total']} rader "
            f"i `{table}.{column}`."
        ),
    }


def _body_battery_charge_fill_stats(db: Session) -> Dict[str, int]:
    total = db.query(BodyBattery).count()
    charged = db.query(BodyBattery).filter(BodyBattery.body_battery_charged.isnot(None)).count()
    return {"total": total, "filled": charged}


def _performance_field_fill_stats(db: Session, column: str) -> Dict[str, int]:
    total = db.query(GarminPerformanceMetric).count()
    col = getattr(GarminPerformanceMetric, column)
    filled = db.query(GarminPerformanceMetric).filter(col.isnot(None)).count()
    return {"total": total, "filled": filled}


def _stored_metric_availability(
    key: str,
    definition: Dict[str, Any],
    table_counts: Dict[Any, int],
    db: Optional[Session] = None,
) -> Dict[str, str]:
    if key in UNSUPPORTED_METRICS:
        return {"availability": "unsupported", "availability_reason": UNSUPPORTED_METRICS[key]}
    if key in NOT_INGESTED_METRICS:
        return {"availability": "not_ingested", "availability_reason": NOT_INGESTED_METRICS[key]}

    model = definition["model"]
    if table_counts.get(model, 0) == 0:
        return {
            "availability": "empty_source",
            "availability_reason": f"Kildetabellen `{model.__tablename__}` er tom i denne databasen.",
        }

    if key in ACTIVITY_BODY_BATTERY_METRICS and db is not None:
        stats = _activity_body_battery_fill_stats(db)
        column = ACTIVITY_BODY_BATTERY_METRICS[key]
        filled = stats["start_filled"] if column == "body_battery_start" else stats["delta_filled"]
        if filled == 0:
            return {
                "availability": "empty_source",
                "availability_reason": (
                    "Ingen aktiviteter har lagret Body Battery ennå. "
                    "Garmin activity summary mangler ofte differenceBodyBattery; "
                    "kjør training_effect-sync eller wellness-backfill for å utlede fra daglig tidsserie."
                ),
            }
        return {
            "availability": "supported",
            "availability_reason": (
                f"Data for {filled}/{stats['total']} aktiviteter. "
                "Verdier kan komme fra Garmin summary eller utledes fra daglig wellness-tidsserie."
            ),
        }

    if key == GRADE_ADJUSTED_PACE_METRIC and db is not None:
        stats = _grade_adjusted_pace_fill_stats(db)
        if stats["filled"] == 0:
            return {
                "availability": "empty_source",
                "availability_reason": (
                    f"{GRADE_ADJUSTED_PACE_EMPTY_REASON} "
                    f"0/{stats['total']} aktiviteter har verdi i denne databasen."
                ),
            }
        return {
            "availability": "supported",
            "availability_reason": (
                f"Grade Adjusted Pace lagret for {stats['filled']}/{stats['total']} aktiviteter "
                "(Garmin avgGradeAdjustedSpeed når tilgjengelig, ellers FIT/Minetti; eksponert som M:SS/km)."
            ),
        }

    if key.startswith("body_battery.") and key in NOT_INGESTED_METRICS:
        if db is not None:
            stats = _body_battery_charge_fill_stats(db)
            if stats["filled"] == 0:
                return {
                    "availability": "not_ingested",
                    "availability_reason": body_battery_not_ingested_reason(db, key),
                }
        return {
            "availability": "not_ingested",
            "availability_reason": NOT_INGESTED_METRICS[key],
        }

    if key == "activity.training_readiness_score" and db is not None:
        stats = _activity_column_fill_stats(db, "training_readiness_score")
        if stats["filled"] == 0:
            return {
                "availability": "computed",
                "availability_reason": (
                    "Ikke lagret på aktiviteter ennå, men kan beregnes lokalt via "
                    "TrainingReadinessService (søvn/HRV/form). Kjør health backfill --readiness-only."
                ),
            }
        return {
            "availability": "supported",
            "availability_reason": (
                f"Training readiness lagret for {stats['filled']}/{stats['total']} aktiviteter "
                "(beregnet lokalt eller fra Garmin)."
            ),
        }

    stamina_columns = {
        "activity.begin_potential_stamina": ("begin_potential_stamina", "beginPotentialStamina"),
        "activity.end_potential_stamina": ("end_potential_stamina", "endPotentialStamina"),
        "activity.min_available_stamina": ("min_available_stamina", "minAvailableStamina"),
    }
    if key in stamina_columns and db is not None:
        column, garmin_field = stamina_columns[key]
        stats = _activity_column_fill_stats(db, column)
        if stats["filled"] == 0:
            return {
                "availability": "not_ingested",
                "availability_reason": activity_summary_not_ingested_reason(db, key, garmin_field),
            }

    if key == "activity.recovery_time" and db is not None:
        stats = _activity_column_fill_stats(db, "recovery_time")
        if stats["filled"] == 0:
            return {
                "availability": "not_ingested",
                "availability_reason": activity_summary_not_ingested_reason(
                    db, key, "recoveryTime/timeToRecover"
                ),
            }

    performance_columns = {
        "performance.fitness_age": "fitness_age",
        "performance.endurance_score": "endurance_score",
        "performance.endurance_classification": "endurance_classification",
        "performance.hill_score": "hill_score",
        "performance.hill_endurance_score": "hill_endurance_score",
        "performance.hill_strength_score": "hill_strength_score",
    }
    if key in performance_columns and db is not None:
        stats = _performance_field_fill_stats(db, performance_columns[key])
        if stats["filled"] == 0 and key in NOT_INGESTED_METRICS and db is not None:
            return {
                "availability": "not_ingested",
                "availability_reason": performance_not_ingested_reason(db, key),
            }

    sleep_detail_keys = {
        "sleep.average_spo2",
        "sleep.lowest_spo2",
        "sleep.average_heart_rate",
        "sleep.lowest_heart_rate",
        "sleep.highest_heart_rate",
        "sleep.heart_rate_variability",
        "sleep.recovery_score",
        "sleep.movement_score",
        "sleep.restless_moments",
        "sleep.sleep_latency",
    }
    if key in sleep_detail_keys and db is not None:
        fill_availability = _stored_column_fill_availability(definition, db)
        if fill_availability is not None and fill_availability["availability"] == "empty_source":
            fill_availability["availability_reason"] = sleep_vital_empty_source_reason(db, key)
        if fill_availability is not None:
            return fill_availability

    if db is not None:
        fill_availability = _stored_column_fill_availability(definition, db)
        if fill_availability is not None:
            return fill_availability

    return {
        "availability": "supported",
        "availability_reason": "Forventes å få verdi når kilde- og aktivitetsdata finnes.",
    }


def _derived_metric_availability(
    key: str,
    definition: Dict[str, Any],
    table_counts: Dict[Any, int],
) -> Dict[str, str]:
    if key in UNSUPPORTED_METRICS:
        return {"availability": "unsupported", "availability_reason": UNSUPPORTED_METRICS[key]}
    if key in DERIVED_EMPTY_SOURCE_DEPENDENCIES:
        model, reason = DERIVED_EMPTY_SOURCE_DEPENDENCIES[key]
        if table_counts.get(model, 0) == 0:
            return {"availability": "empty_source", "availability_reason": reason}
    return {
        "availability": "computed",
        "availability_reason": "Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.",
    }


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
        latest_hrv_row = (
            db.query(HRV)
            .filter(HRV.rmssd.isnot(None))
            .order_by(HRV.measurement_date.desc(), HRV.measurement_time.desc())
            .first()
        )
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
            "latest_threshold": enrich_athlete_threshold_payload(threshold),
            "latest_garmin_performance": _garmin_performance_payload(latest_perf),
            "latest_hrv": {
                **hrv_mcp_recovery_payload(latest_hrv_row),
                "date": latest_hrv_row.measurement_date.isoformat() if latest_hrv_row else None,
            },
            "recovery_tools": {
                "daily_context": "daily_recovery_context",
                "readiness_snapshot": "readiness_snapshot",
                "coaching_check": "training_readiness_check",
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

        derived = McpDerivedMetricsService(db, storage)
        composites = derived.get_readiness_composites(end_date)
        readiness_composites = {
            "readiness.total_score": _latest_derived_metric_value(derived, "readiness.total_score", end_date),
            "readiness_score": composites.get("readiness_score"),
            "recovery_score": composites.get("recovery_score"),
            "fitness_tsb": composites.get("fitness_tsb"),
            "recovery_hrv_delta_pct": composites.get("recovery_hrv_delta_pct"),
            "recovery.predicted_hours_to_baseline": _latest_derived_metric_value(
                derived,
                "recovery.predicted_hours_to_baseline",
                end_date,
            ),
        }

        return {
            "date": end_date.isoformat(),
            "recommendation": recommendation,
            "banister": banister,
            "hrv_guidance": hrv,
            "flags": flags,
            "recovery_context": _daily_recovery_context(end_date, db),
            "readiness_composites": readiness_composites,
            "metric_links": {
                "garmin_readiness": "readiness.total_score",
                "coaching_readiness": "readiness_score",
                "hrv_raw": "health.hrv_rmssd",
                "hrv_baseline": "recovery.hrv_baseline",
                "hrv_delta": "recovery.hrv_delta_pct",
            },
            "related_tools": {
                "daily_recovery_context": "Full daglig recovery-kontekst.",
                "readiness_snapshot": "Komplette PPAP-kompositter + recovery.",
            },
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
            "recovery_context": _activity_recovery_context(activity, db),
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
                enrich_dict_pace_fields(
                    {
                        **match,
                        "pace_sec_per_km": _activity_pace(matched),
                        "average_heart_rate": matched.average_heart_rate,
                        "training_effect": matched.total_training_effect,
                        "vo2_max": matched.vo2_max,
                    },
                    user_key="average_pace",
                )
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


def metric_glossary(
    metric_key: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
) -> Dict[str, Any]:
    """Return coaching glossary for metrics — definitions, interpretation and caveats."""
    if metric_key:
        canonical, alias_of = _resolve_metric_key(metric_key)
        result = build_metric_glossary(metric_key=canonical, category=category, search=search)
        if alias_of and result.get("status") == "ok":
            entry = result["entry"]
            entry["requested_metric_key"] = alias_of
            entry["canonical_key"] = canonical
            entry["alias_note"] = f"{alias_of} er alias for {canonical}."
        return result
    result = build_metric_glossary(metric_key=metric_key, category=category, search=search)
    if result.get("status") == "ok" and "entries" in result:
        result["semantic_links"] = METRIC_SEMANTIC_LINKS
        result["metric_aliases"] = METRIC_KEY_ALIASES
    return result



def daily_recovery_context(target_date: Optional[str] = None) -> Dict[str, Any]:
    """Daglig recovery-bilde: HRV, søvn, puls, stress, body battery og readiness for én dato."""
    day = _parse_date(target_date) if target_date else date.today()
    with training_context() as (db, _storage):
        return {
            "status": "ok",
            **_daily_recovery_context(day, db),
        }


def readiness_snapshot(target_date: Optional[str] = None) -> Dict[str, Any]:
    """PPAP readiness-kompositter + recovery-kontekst og lenker til timeseries-nøkler."""
    day = _parse_date(target_date) if target_date else date.today()
    with training_context() as (db, storage):
        derived = McpDerivedMetricsService(db, storage)
        return {
            "status": "ok",
            "date": day.isoformat(),
            "composites": derived.get_readiness_composites(day),
            "recovery_context": _daily_recovery_context(day, db),
            "metric_links": {
                "garmin_total": "readiness.total_score",
                "garmin_sleep_component": "readiness.sleep_component",
                "garmin_hrv_component": "readiness.hrv_component",
                "garmin_form_component": "readiness.form_component",
                "coaching_readiness": "readiness_score",
                "coaching_recovery": "recovery_score",
                "activity_stored": "activity.training_readiness_score",
                "hrv_raw": "health.hrv_rmssd",
            },
            "glossary_hint": "Bruk metric_glossary for readiness.total_score vs readiness_score.",
        }


def coaching_decision_snapshot(target_date: Optional[str] = None) -> Dict[str, Any]:
    """Samlet coaching-beslutningsbilde: consistency, event readiness, limiters, anbefalt økt."""
    day = _parse_date(target_date) if target_date else date.today()
    with training_context() as (db, storage):
        from ..services.ppap_metrics_service import PpapMetricsService
        from ..services.coaching_decision_metrics_service import CoachingDecisionMetricsService
        service = CoachingDecisionMetricsService(db, PpapMetricsService(db, storage))
        return service.build_coaching_snapshot(day)


def metric_catalog() -> Dict[str, Any]:
    with training_context() as (db, _storage):
        table_counts = _model_table_counts(db)
        db_for_availability = db

    metrics = []
    alias_index = _metric_alias_index()
    for key, definition in sorted(METRIC_CATALOG.items()):
        gloss = get_glossary_entry(key)
        entry = {
            "key": key,
            "category": definition["category"],
            "unit": definition["unit"],
            "source": definition["model"].__tablename__,
            "scope": "stored",
            "summary": gloss.get("definition"),
            **_stored_metric_availability(key, definition, table_counts, db_for_availability),
        }
        if key in alias_index:
            entry["aliases"] = sorted(alias_index[key])
        if key in METRIC_KEY_ALIASES:
            entry["canonical_key"] = METRIC_KEY_ALIASES[key]
        metrics.append(entry)
    for key, definition in sorted(DERIVED_METRIC_CATALOG.items()):
        gloss = get_glossary_entry(key)
        entry = {
            "key": key,
            "category": definition["category"],
            "unit": definition["unit"],
            "scope": definition["scope"],
            "source": "derived",
            "heuristic": definition.get("heuristic", False),
            "summary": gloss.get("definition"),
            **_derived_metric_availability(key, definition, table_counts),
        }
        if key in alias_index:
            entry["aliases"] = sorted(alias_index[key])
        if key in METRIC_KEY_ALIASES:
            entry["canonical_key"] = METRIC_KEY_ALIASES[key]
        metrics.append(entry)
    categories = sorted({m["category"] for m in metrics})
    scopes = sorted({m["scope"] for m in metrics if m.get("scope")})
    stored_count = sum(1 for m in metrics if m.get("scope") == "stored")
    derived_count = len(metrics) - stored_count
    return {
        "schema_version": "ppap-3",
        "metrics": metrics,
        "count": len(metrics),
        "stored_metric_count": stored_count,
        "derived_metric_count": derived_count,
        "categories": categories,
        "scopes": scopes,
        "availability_states": ["supported", "computed", "not_ingested", "empty_source", "unsupported"],
        "semantic_links": METRIC_SEMANTIC_LINKS,
        "metric_aliases": METRIC_KEY_ALIASES,
        "glossary_hint": "Bruk metric_glossary eller treningsanalyse://metric-glossary.",
        "timeseries_hint": "Use query_metric_timeseries with one of these whitelisted metric keys.",
        "recovery_tools": {
            "daily_recovery_context": "Daglig HRV/søvn/stress/body battery/readiness.",
            "readiness_snapshot": "Kompositter + recovery_context + metric_links.",
            "activity_deep_dive": "Recovery_context knyttet til én aktivitet.",
        },
        "speed_pace_audit": {
            "user_facing_mps_metrics": audit_user_facing_speed_units(metrics),
            "display_policy": (
                "Speed metrics expose km/h; pace metrics expose M:SS/km with pace_sec_per_km "
                "as numeric side field; m/s only as speed_mps_internal."
            ),
        },
    }


def _run_query_metric_timeseries(
    metric_key: str,
    start_date: Optional[str],
    end_date: Optional[str],
    limit: int,
    *,
    db: Session,
    storage: DataStorage,
    service: McpDerivedMetricsService,
) -> Dict[str, Any]:
    """Kjerne for query_metric_timeseries mot en gitt db/storage/service.

    Lar kallere (f.eks. metric_quality_report) gjenbruke én session + én
    McpDerivedMetricsService på tvers av mange metrikker, slik at instans-cacher
    (load-serie, coaching, duration-curve) beholdes.
    """
    requested_key = metric_key
    metric_key, alias_of = _resolve_metric_key(metric_key)

    if metric_key in DERIVED_METRIC_CATALOG:
        limit = max(1, min(int(limit), 5000))
        try:
            result = service.query_timeseries(
                metric_key,
                start_date=_parse_date(start_date) if start_date else None,
                end_date=_parse_date(end_date) if end_date else None,
                limit=limit,
            )
        except Exception as exc:
            result = {
                "status": "error",
                "metric_key": metric_key,
                "message": str(exc),
            }
        if alias_of:
            result["requested_metric_key"] = requested_key
            result["canonical_key"] = metric_key
        if result.get("status") == "ok":
            result["points"] = [
                enrich_derived_metric_point(metric_key, point)
                for point in result.get("points", [])
            ]
            display_unit = mcp_display_unit(metric_key)
            if display_unit:
                result["unit"] = display_unit
                result["display_unit"] = display_unit
        return result

    if metric_key not in METRIC_CATALOG:
        return {
            "status": "unknown_metric",
            "metric_key": requested_key,
            "available_metric_count": len(METRIC_CATALOG) + len(DERIVED_METRIC_CATALOG),
        }
    definition = METRIC_CATALOG[metric_key]
    model = definition["model"]
    date_field = getattr(model, definition["date_field"])
    limit = max(1, min(int(limit), 5000))
    start = _parse_date(start_date) if start_date else None
    end = _parse_date(end_date) if end_date else None

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
    points = [_metric_point(row, definition, metric_key) for row in reversed(rows)]
    points = [point for point in points if point["value"] is not None]
    display_unit = mcp_display_unit(metric_key, definition.get("column")) or definition["unit"]
    result = {
        "status": "ok",
        "metric_key": metric_key,
        "category": definition["category"],
        "unit": display_unit,
        "display_unit": display_unit,
        "points": points,
        "count": len(points),
    }
    if alias_of:
        result["requested_metric_key"] = requested_key
        result["canonical_key"] = metric_key
    return result


def query_metric_timeseries(
    metric_key: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 365,
) -> Dict[str, Any]:
    with training_context() as (db, storage):
        service = McpDerivedMetricsService(db, storage)
        return _run_query_metric_timeseries(
            metric_key, start_date, end_date, limit,
            db=db, storage=storage, service=service,
        )


def _latest_derived_metric_value(
    service: McpDerivedMetricsService,
    metric_key: str,
    day: date,
) -> Optional[float]:
    series = service.query_timeseries(metric_key, end_date=day, limit=1)
    if series.get("status") != "ok":
        return None
    points = series.get("points") or []
    if not points:
        return None
    value = points[-1].get("value")
    return float(value) if isinstance(value, (int, float)) else None


def metric_quality_report(
    target_date: Optional[str] = None,
    lookback_days: int = 14,
    markdown: bool = False,
) -> Dict[str, Any]:
    """
    Kvalitetsrapport for alle metrikker i metric_catalog: status, siste verdi, dato, heuristikk.
    """
    lookback_days = max(1, min(int(lookback_days), 90))
    ref = _parse_date(target_date) if target_date else date.today()
    catalog = metric_catalog()
    # Gjenbruk én DB-session + én McpDerivedMetricsService for HELE rapporten, slik at
    # tunge beregninger (CTL/ATL/TSB-serie, coaching/Banister, duration-curves) caches
    # på tvers av alle metrikkene i stedet for å bygges på nytt per metrikk.
    with training_context() as (db, storage):
        service = McpDerivedMetricsService(db, storage)

        def query_fn(key, start_date=None, end_date=None, limit=365):
            return _run_query_metric_timeseries(
                key, start_date, end_date, limit,
                db=db, storage=storage, service=service,
            )

        report = build_metric_quality_report(
            catalog_metrics=catalog["metrics"],
            query_timeseries_fn=query_fn,
            reference_date=ref,
            lookback_days=lookback_days,
        )
    if markdown:
        report["markdown"] = format_metric_quality_markdown(report)
    report["semantic_links"] = METRIC_SEMANTIC_LINKS
    report["metric_aliases"] = METRIC_KEY_ALIASES
    return report


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


def _metric_point(row: Any, definition: Dict[str, Any], metric_key: str) -> Dict[str, Any]:
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
    elif definition.get("derived") == "grade_adjusted_pace":
        value = _grade_adjusted_pace(row)
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
    return enrich_stored_metric_point(metric_key, point, row, definition)


def _activity_summary(activity: Activity) -> Dict[str, Any]:
    summary = {
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
        "recovery": _activity_recovery_fields(activity),
    }
    if summary["pace_sec_per_km"] is not None:
        enrich_dict_pace_fields(summary, user_key="average_pace")
    return enrich_activity_summary_speed_fields(summary)


def _stored_body_battery_start(activity: Activity) -> Dict[str, Any]:
    value = activity.body_battery_start
    if value is not None and value < 0:
        return {
            "value": None,
            "availability": "unavailable",
            "source": "none",
            "reason": "Markert som utilgjengelig i activities (f.eks. -1 fra precompute).",
        }
    if value is not None:
        return {
            "value": round(float(value), 1),
            "availability": "estimated",
            "source": "activity_db",
            "reason": "Lagret per aktivitet (wellness-tidsserie eller estimat).",
        }
    return {
        "value": None,
        "availability": "missing",
        "source": "none",
        "reason": "Ikke lagret for aktiviteten ennå.",
    }


def _stored_body_battery_delta(activity: Activity) -> Dict[str, Any]:
    value = activity.activity_body_battery_delta
    if value is not None:
        return {
            "value": round(float(value), 1),
            "availability": "supported",
            "source": "garmin_activity_summary",
            "reason": "Lagret per aktivitet (Garmin summary eller wellness-tidsserie).",
        }
    return {
        "value": None,
        "availability": "missing",
        "source": "none",
        "reason": "Ikke lagret for aktiviteten ennå.",
    }


def _stored_training_readiness(activity: Activity) -> Dict[str, Any]:
    value = activity.training_readiness_score
    if value is not None:
        return {
            "value": round(float(value), 1),
            "availability": "stored",
            "source": "activity_db",
            "reason": "Lagret på aktiviteten etter TrainingReadinessService-beregning.",
        }
    return {
        "value": None,
        "availability": "missing",
        "source": "none",
        "reason": "Ikke lagret på aktiviteten.",
    }


def _activity_recovery_fields(activity: Activity) -> Dict[str, Any]:
    return {
        "body_battery_start": _stored_body_battery_start(activity),
        "activity_body_battery_delta": _stored_body_battery_delta(activity),
        "training_readiness_score": _stored_training_readiness(activity),
    }


def _resolve_activity_training_readiness(activity: Activity, db: Session, activity_day: date) -> Dict[str, Any]:
    stored = _stored_training_readiness(activity)
    if stored["value"] is not None:
        from ..services.training_readiness_service import TrainingReadinessService

        service = TrainingReadinessService(db)
        stored["readiness_status"] = service._get_readiness_status(stored["value"])
        return stored

    try:
        from ..services.training_readiness_service import (
            TrainingReadinessService,
            is_robust_training_readiness,
        )

        service = TrainingReadinessService(db)
        computed = service.calculate_training_readiness(activity_day)
        if (
            computed
            and computed.get("total_score") is not None
            and "error" not in computed
            and is_robust_training_readiness(computed)
        ):
            return {
                "value": round(float(computed["total_score"]), 1),
                "readiness_status": computed.get("readiness_status"),
                "components": computed.get("components"),
                "availability": "computed",
                "source": "training_readiness_service",
                "reason": "Beregnet daglig readiness fra lokal søvn/HRV/form-data.",
            }
    except Exception:
        pass

    return {
        "value": None,
        "availability": "missing",
        "source": "none",
        "reason": "Ingen robust lagret eller beregnbar readiness for aktivitetsdagen.",
    }


def _derived_body_battery_end(start: Dict[str, Any], delta: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if start.get("value") is None or delta.get("value") is None:
        return None
    end_value = round(float(start["value"]) + float(delta["value"]), 1)
    return {
        "value": end_value,
        "availability": "computed",
        "source": "derived_from_start_and_delta",
        "reason": "Beregnet som body_battery_start + activity_body_battery_delta.",
    }


def _resolve_daily_training_readiness(db: Session, activity_day: date) -> Dict[str, Any]:
    stored_activity = (
        db.query(Activity)
        .filter(
            func.date(Activity.start_time) == activity_day,
            Activity.training_readiness_score.isnot(None),
        )
        .order_by(Activity.start_time.desc())
        .first()
    )
    if stored_activity is not None:
        return _resolve_activity_training_readiness(stored_activity, db, activity_day)

    try:
        from ..services.training_readiness_service import TrainingReadinessService

        service = TrainingReadinessService(db)
        computed = service.calculate_training_readiness(activity_day)
        if computed and computed.get("total_score") is not None and "error" not in computed:
            return {
                "value": round(float(computed["total_score"]), 1),
                "readiness_status": computed.get("readiness_status"),
                "components": computed.get("components"),
                "availability": "computed",
                "source": "training_readiness_service",
                "reason": "Beregnet daglig readiness fra lokal søvn/HRV/form-data.",
            }
    except Exception:
        pass

    return {
        "value": None,
        "availability": "missing",
        "source": "none",
        "reason": "Ingen lagret eller beregnbar readiness for dagen.",
    }


def _hrv_baseline_for_day(db: Session, activity_day: date) -> tuple[Optional[float], Optional[float]]:
    baseline_rows = (
        db.query(HRV.rmssd)
        .filter(
            HRV.measurement_date < activity_day,
            HRV.rmssd.isnot(None),
        )
        .order_by(HRV.measurement_date.desc())
        .limit(7)
        .all()
    )
    baseline_values = [float(row.rmssd) for row in baseline_rows if row.rmssd is not None]
    baseline_avg = sum(baseline_values) / len(baseline_values) if baseline_values else None
    hrv_delta_pct = None
    hrv = (
        db.query(HRV)
        .filter(
            HRV.measurement_date == activity_day,
            HRV.rmssd.isnot(None),
        )
        .order_by(HRV.measurement_time.desc())
        .first()
    )
    if hrv and hrv.rmssd is not None and baseline_avg not in (None, 0):
        hrv_delta_pct = ((float(hrv.rmssd) / baseline_avg) - 1.0) * 100.0
    return (
        round(baseline_avg, 1) if baseline_avg is not None else None,
        round(hrv_delta_pct, 1) if hrv_delta_pct is not None else None,
    )


def _sleep_recovery_payload(sleep: Optional[Sleep]) -> Dict[str, Any]:
    return {
        "total_sleep_time_s": sleep.total_sleep_time if sleep else None,
        "sleep_score": sleep.sleep_score if sleep else None,
        "overall_score": sleep.overall_score if sleep else None,
        "sleep_efficiency": sleep.sleep_efficiency if sleep else None,
        "stress_score": sleep.stress_score if sleep else None,
        "recovery_score": sleep.recovery_score if sleep else None,
        "source": "local_db" if sleep else "none",
        "availability": "supported" if sleep else "missing",
        "reason": (
            "Søvn fra lokal database (synk fra Garmin)."
            if sleep
            else "Ingen søvn registrert for dagen."
        ),
    }


def _resting_hr_recovery_payload(rhr: Optional[RestingHeartRate]) -> Dict[str, Any]:
    return {
        "value": rhr.resting_heart_rate if rhr else None,
        "source": "local_db" if rhr else "none",
        "availability": "supported" if rhr else "missing",
        "reason": (
            "Hvilepuls fra lokal database (synk fra Garmin)."
            if rhr
            else "Ingen hvilepuls registrert for dagen."
        ),
    }


def _stress_recovery_payload(stress: Optional[Stress]) -> Dict[str, Any]:
    return {
        "stress_level": stress.stress_level if stress else None,
        "high_stress_time_s": stress.high_stress_time if stress else None,
        "rest_time_s": stress.rest_time if stress else None,
        "source": "local_db" if stress else "none",
        "availability": "supported" if stress else "missing",
        "reason": (
            "Daglig stress fra lokal database (synk fra Garmin)."
            if stress
            else "Ingen stress registrert for dagen."
        ),
    }


def _body_battery_recovery_payload(
    body_battery: Optional[BodyBattery],
    activity: Optional[Activity] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "daily_max": body_battery.max_body_battery if body_battery else None,
        "daily_min": body_battery.min_body_battery if body_battery else None,
        "daily_net_charge": body_battery.net_charge if body_battery else None,
        "daily_source": "local_db" if body_battery else "none",
        "daily_availability": "supported" if body_battery else "missing",
        "daily_reason": (
            "Daglig Body Battery fra lokal database (synk fra Garmin)."
            if body_battery
            else "Ingen daglig Body Battery registrert for dagen."
        ),
    }
    if activity is not None:
        start = _stored_body_battery_start(activity)
        delta = _stored_body_battery_delta(activity)
        payload.update(
            {
                "start": start,
                "delta": delta,
                "end_derived": _derived_body_battery_end(start, delta),
            }
        )
    return payload


def _daily_recovery_context(
    activity_day: date,
    db: Session,
    *,
    activity: Optional[Activity] = None,
) -> Dict[str, Any]:
    sleep = db.query(Sleep).filter(Sleep.sleep_date == activity_day).first()
    hrv = (
        db.query(HRV)
        .filter(
            HRV.measurement_date == activity_day,
            HRV.rmssd.isnot(None),
        )
        .order_by(HRV.measurement_time.desc())
        .first()
    )
    rhr = (
        db.query(RestingHeartRate)
        .filter(
            RestingHeartRate.measurement_date == activity_day,
            RestingHeartRate.resting_heart_rate.isnot(None),
        )
        .order_by(RestingHeartRate.measurement_date.desc())
        .first()
    )
    stress = db.query(Stress).filter(Stress.stress_date == activity_day).first()
    body_battery = db.query(BodyBattery).filter(BodyBattery.date == activity_day).first()
    perf = (
        db.query(GarminPerformanceMetric)
        .filter(func.date(GarminPerformanceMetric.date) == activity_day)
        .first()
    )
    baseline_7d, hrv_delta_pct = _hrv_baseline_for_day(db, activity_day)

    training_readiness = (
        _resolve_activity_training_readiness(activity, db, activity_day)
        if activity is not None
        else _resolve_daily_training_readiness(db, activity_day)
    )

    return {
        "date": activity_day.isoformat(),
        "hrv": hrv_mcp_recovery_payload(
            hrv,
            baseline_7d=baseline_7d,
            delta_pct=hrv_delta_pct,
        ),
        "sleep": _sleep_recovery_payload(sleep),
        "resting_heart_rate": _resting_hr_recovery_payload(rhr),
        "stress": _stress_recovery_payload(stress),
        "body_battery": _body_battery_recovery_payload(body_battery, activity),
        "training_readiness": training_readiness,
        "garmin_performance": _garmin_performance_payload(perf),
        "metric_links": {
            "hrv_timeseries": "health.hrv_rmssd",
            "readiness_timeseries": "readiness.total_score",
            "sleep_score_timeseries": "health.sleep_overall_score",
            "stress_timeseries": "health.stress_level",
        },
    }


def _activity_recovery_context(activity: Activity, db: Session) -> Dict[str, Any]:
    if activity.start_time is None:
        return {}
    return _daily_recovery_context(activity.start_time.date(), db, activity=activity)


def _garmin_performance_payload(row: Optional[GarminPerformanceMetric]) -> Dict[str, Any]:
    if row is None:
        return {
            "source": "none",
            "availability": "missing",
            "reason": "Ingen Garmin performance-metrics synket for dagen.",
        }
    return {
        "source": "local_db",
        "availability": "supported",
        "reason": "Garmin performance-metrics fra lokal database (synk).",
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
        enrich_dict_pace_fields(
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
        )
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
            enrich_dict_pace_fields(
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


def _grade_adjusted_pace(activity: Activity) -> Optional[float]:
    return _pace_from_speed(activity.avg_grade_adjusted_speed)


def _pace_from_speed(speed_mps: Optional[float]) -> Optional[float]:
    return mps_to_pace_sec_per_km(speed_mps)


def _readable_date(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.strftime("%A, %Y-%m-%d %H:%M")


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()
