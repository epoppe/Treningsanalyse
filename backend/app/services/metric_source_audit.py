"""Audit av faktisk datakilde-tilgjengelighet i lokal DB (uten ny Garmin-nedlasting)."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from ..database.models.activity import Activity, GarminPerformanceMetric
from ..database.models.body_battery import BodyBattery
from ..database.models.sleep import Sleep


def _coerce_dict(value: Any) -> Optional[dict]:
    return value if isinstance(value, dict) else None


def audit_garmin_performance_raw_sources(db: Session) -> Dict[str, Any]:
    """Tell rader der lagret raw_* JSON faktisk inneholder Garmin-verdier."""
    rows = db.query(
        GarminPerformanceMetric.raw_maxmet,
        GarminPerformanceMetric.raw_endurance_score,
        GarminPerformanceMetric.raw_hill_score,
        GarminPerformanceMetric.fitness_age,
        GarminPerformanceMetric.endurance_score,
        GarminPerformanceMetric.hill_score,
        GarminPerformanceMetric.hill_endurance_score,
        GarminPerformanceMetric.hill_strength_score,
    ).all()

    total = len(rows)
    raw_fitness_age_rows = 0
    raw_endurance_rows = 0
    raw_hill_rows = 0
    filled = {
        "fitness_age": 0,
        "endurance_score": 0,
        "hill_score": 0,
        "hill_endurance_score": 0,
        "hill_strength_score": 0,
    }

    for row in rows:
        raw_maxmet = _coerce_dict(row.raw_maxmet)
        if raw_maxmet:
            for section_key in ("generic", "cycling", "running"):
                section = raw_maxmet.get(section_key)
                if isinstance(section, dict) and section.get("fitnessAge") is not None:
                    raw_fitness_age_rows += 1
                    break

        endurance_payload = _coerce_dict(row.raw_endurance_score)
        if endurance_payload and (
            endurance_payload.get("overallScore") is not None
            or endurance_payload.get("enduranceScore") is not None
        ):
            raw_endurance_rows += 1

        hill_payload = _coerce_dict(row.raw_hill_score)
        if hill_payload and (
            hill_payload.get("overallScore") is not None
            or hill_payload.get("hillScore") is not None
            or hill_payload.get("enduranceScore") is not None
            or hill_payload.get("strengthScore") is not None
        ):
            raw_hill_rows += 1

        if row.fitness_age is not None:
            filled["fitness_age"] += 1
        if row.endurance_score is not None:
            filled["endurance_score"] += 1
        if row.hill_score is not None:
            filled["hill_score"] += 1
        if row.hill_endurance_score is not None:
            filled["hill_endurance_score"] += 1
        if row.hill_strength_score is not None:
            filled["hill_strength_score"] += 1

    return {
        "total_rows": total,
        "raw_fitness_age_rows": raw_fitness_age_rows,
        "raw_endurance_rows": raw_endurance_rows,
        "raw_hill_rows": raw_hill_rows,
        "filled": filled,
    }


def performance_not_ingested_reason(db: Session, metric_key: str) -> str:
    audit = audit_garmin_performance_raw_sources(db)
    total = audit["total_rows"]
    if metric_key == "performance.fitness_age":
        return (
            f"Garmin raw_maxmet er synket for {total} dager, men fitnessAge er null i alle rader "
            f"({audit['raw_fitness_age_rows']}/{total} med verdi i JSON)."
        )
    if metric_key == "performance.endurance_score":
        return (
            f"Garmin raw_endurance_score er synket for {total} dager, men overallScore er null i alle rader "
            f"({audit['raw_endurance_rows']}/{total} med verdi i JSON)."
        )
    if metric_key == "performance.endurance_classification":
        return performance_not_ingested_reason(db, "performance.endurance_score")
    if metric_key in {
        "performance.hill_score",
        "performance.hill_endurance_score",
        "performance.hill_strength_score",
    }:
        return (
            f"Garmin raw_hill_score er synket for {total} dager, men hill-score-felter er null i alle rader "
            f"({audit['raw_hill_rows']}/{total} med verdi i JSON)."
        )
    return "Garmin performance-felt mangler i lokal database."


def audit_body_battery_charge_sources(db: Session) -> Dict[str, int]:
    total = db.query(BodyBattery).count()
    charged = db.query(BodyBattery).filter(BodyBattery.body_battery_charged.isnot(None)).count()
    drained = db.query(BodyBattery).filter(BodyBattery.body_battery_drained.isnot(None)).count()
    net = db.query(BodyBattery).filter(BodyBattery.net_charge.isnot(None)).count()
    max_min = db.query(BodyBattery).filter(
        BodyBattery.max_body_battery.isnot(None),
        BodyBattery.min_body_battery.isnot(None),
    ).count()
    return {
        "total": total,
        "charged": charged,
        "drained": drained,
        "net_charge": net,
        "max_min_only": max_min,
    }


def body_battery_not_ingested_reason(db: Session, metric_key: str) -> str:
    stats = audit_body_battery_charge_sources(db)
    total = stats["total"]
    return (
        f"Body Battery charged/drained krever wellness-tidsserie (body_battery_values_array). "
        f"Lokal DB har {total} daglige rader med max/min, men 0/{total} med charged/drained — "
        f"tidsserien ble ikke persistert ved sync og finnes ikke i lokale filer."
    )


def audit_model_column_sources(db: Session, model: Any, column: str) -> Dict[str, int]:
    col = getattr(model, column)
    total = db.query(model).count()
    filled = db.query(model).filter(col.isnot(None)).count()
    return {"total": total, "filled": filled}


def audit_activity_column_sources(db: Session, column: str) -> Dict[str, int]:
    return audit_model_column_sources(db, Activity, column)


_SLEEP_DETAIL_DETAILED_KEYS: Dict[str, Tuple[str, ...]] = {
    "sleep.average_spo2": ("average_sp_o2_value", "averageSpo2", "average_spo2", "avgSpo2"),
    "sleep.lowest_spo2": ("lowest_sp_o2_value", "lowestSpo2", "lowest_spo2", "minSpo2"),
    "sleep.average_heart_rate": ("average_sp_o2_hr_sleep", "averageHeartRate", "average_heart_rate"),
    "sleep.lowest_heart_rate": ("lowestHeartRate", "lowest_heart_rate", "minHeartRate"),
    "sleep.highest_heart_rate": ("highestHeartRate", "highest_heart_rate", "maxHeartRate"),
    "sleep.heart_rate_variability": ("heartRateVariability", "heart_rate_variability", "averageHrv"),
    "sleep.recovery_score": ("recovery_score", "recoveryScore"),
    "sleep.movement_score": ("movement_score", "movementScore"),
    "sleep.restless_moments": ("restless_moments", "restlessMoments", "restlessMomentCount"),
    "sleep.sleep_latency": (
        "sleepLatencyInSeconds",
        "sleepLatencySeconds",
        "timeToFallAsleepSeconds",
        "sleep_latency",
        "sleepLatency",
        "timeToFallAsleep",
    ),
}


def audit_sleep_vital_sources(db: Session, metric_key: str) -> Dict[str, int]:
    """Tell søvn-rader med kolonneverdi vs. nøkkel i lagret detailed_sleep_data."""
    column = metric_key.split(".", 1)[-1]
    col = getattr(Sleep, column)
    total = db.query(Sleep).count()
    filled = db.query(Sleep).filter(col.isnot(None)).count()
    detailed_rows = 0
    detailed_with_key = 0
    detailed_with_value = 0
    keys = _SLEEP_DETAIL_DETAILED_KEYS.get(metric_key, ())
    for (payload,) in db.query(Sleep.detailed_sleep_data).filter(Sleep.detailed_sleep_data.isnot(None)).all():
        if not isinstance(payload, dict):
            continue
        detailed_rows += 1
        for key in keys:
            if key in payload:
                detailed_with_key += 1
                if payload.get(key) is not None:
                    detailed_with_value += 1
                break
    return {
        "total": total,
        "filled": filled,
        "detailed_rows": detailed_rows,
        "detailed_with_key": detailed_with_key,
        "detailed_with_value": detailed_with_value,
    }


def sleep_vital_empty_source_reason(db: Session, metric_key: str) -> str:
    stats = audit_sleep_vital_sources(db, metric_key)
    column = metric_key.split(".", 1)[-1]
    if stats["detailed_with_value"] > 0:
        return (
            f"Kolonne `{column}` i `sleep` har 0/{stats['total']} rader, men "
            f"{stats['detailed_with_value']}/{stats['detailed_rows']} detailed_sleep_data-rader har verdi. "
            "Kjør health backfill --sleep-only."
        )
    if stats["detailed_with_key"] > 0:
        return (
            f"Garmin detailed_sleep_data har nøkkel for {column} i "
            f"{stats['detailed_with_key']}/{stats['detailed_rows']} rader, men alle verdier er null "
            f"(0/{stats['total']} lagret i `sleep.{column}`)."
        )
    if stats["detailed_rows"] == 0:
        return (
            f"Kolonne `{column}` i `sleep` har 0/{stats['total']} rader med verdi. "
            "Garmin daily sleep-sync lagrer ikke dette feltet; kun 0 rader har detailed_sleep_data."
        )
    return (
        f"Kolonne `{column}` i `sleep` har 0/{stats['total']} rader med verdi. "
        f"Garmin detailed_sleep_data ({stats['detailed_rows']} rader) mangler {column} — "
        "krever utvidet sleep-detail-sync, ikke tilgjengelig i eksisterende lokale kilder."
    )


def activity_summary_not_ingested_reason(db: Session, metric_key: str, garmin_field: str) -> str:
    column_map = {
        "activity.recovery_time": "recovery_time",
        "activity.begin_potential_stamina": "begin_potential_stamina",
        "activity.end_potential_stamina": "end_potential_stamina",
        "activity.min_available_stamina": "min_available_stamina",
    }
    column = column_map.get(metric_key, metric_key.split(".", 1)[-1])
    stats = audit_activity_column_sources(db, column)
    return (
        f"Garmin activity summary ({garmin_field}) finnes ikke i FIT/parquet. "
        f"Lokal DB har {stats['filled']}/{stats['total']} aktiviteter med lagret {column}."
    )
