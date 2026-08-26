"""Backfill av helsedatafelter fra eksisterende lokale kilder (ingen Garmin-nedlasting)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database.models.activity import Activity, GarminPerformanceMetric
from ..database.models.body_battery import BodyBattery
from ..database.models.sleep import Sleep
from ..utils.sleep_field_derivation import derive_sleep_fields_from_row
from .training_readiness_service import is_robust_training_readiness


@dataclass
class HealthBackfillResult:
    changed: bool = False
    fixes: List[str] = field(default_factory=list)


@dataclass
class HealthBackfillSummary:
    sleep_rows_updated: int = 0
    performance_rows_updated: int = 0
    activity_rows_updated: int = 0
    readiness_days_updated: int = 0
    readiness_days_skipped: int = 0
    body_battery_rows_updated: int = 0
    field_counts: Dict[str, int] = field(default_factory=dict)
    examples: List[Dict[str, Any]] = field(default_factory=list)


def _apply_missing_fields(target: Any, values: Dict[str, Any], *, prefix: str, result: HealthBackfillResult) -> None:
    for attr, value in values.items():
        if value is None or getattr(target, attr, None) is not None:
            continue
        setattr(target, attr, value)
        result.changed = True
        result.fixes.append(f"{prefix}{attr}={value}")


def apply_sleep_field_backfill(row: Sleep) -> HealthBackfillResult:
    """Fyll manglende søvn-sidefelter fra kolonner og lagret detailed_sleep_data."""
    result = HealthBackfillResult()
    derived = derive_sleep_fields_from_row(row)
    _apply_missing_fields(row, derived, prefix="sleep.", result=result)
    return result


def _coerce_optional_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_fitness_age_from_raw_maxmet(raw_maxmet: Any) -> Optional[float]:
    if not isinstance(raw_maxmet, dict):
        return None
    for section_key in ("generic", "cycling", "running"):
        section = raw_maxmet.get(section_key)
        if not isinstance(section, dict):
            continue
        fitness_age = _coerce_optional_float(section.get("fitnessAge"))
        if fitness_age is not None:
            return fitness_age
    return None


def _extract_endurance_fields(raw_endurance: Any) -> Dict[str, Any]:
    if not isinstance(raw_endurance, dict):
        return {}
    values: Dict[str, Any] = {}
    overall = raw_endurance.get("overallScore")
    if overall is None:
        overall = raw_endurance.get("enduranceScore")
    if overall is not None:
        values["endurance_score"] = _coerce_optional_float(overall)
    classification = raw_endurance.get("classification")
    if classification is not None:
        values["endurance_classification"] = classification
    return values


def _extract_hill_fields(raw_hill: Any) -> Dict[str, Any]:
    if not isinstance(raw_hill, dict):
        return {}
    values: Dict[str, Any] = {}
    for target, keys in (
        ("hill_score", ("overallScore", "hillScore")),
        ("hill_endurance_score", ("enduranceScore", "hillEnduranceScore")),
        ("hill_strength_score", ("strengthScore", "hillStrengthScore")),
    ):
        for key in keys:
            numeric = _coerce_optional_float(raw_hill.get(key))
            if numeric is not None:
                values[target] = numeric
                break
    return values


def apply_garmin_performance_field_backfill(row: GarminPerformanceMetric) -> HealthBackfillResult:
    """Fyll manglende performance-felter fra lagrede raw_* JSON-blobs."""
    result = HealthBackfillResult()
    values: Dict[str, Any] = {}

    if row.fitness_age is None:
        fitness_age = _extract_fitness_age_from_raw_maxmet(row.raw_maxmet)
        if fitness_age is not None:
            values["fitness_age"] = fitness_age

    values.update(_extract_endurance_fields(row.raw_endurance_score))
    values.update(_extract_hill_fields(row.raw_hill_score))

    filtered = {
        attr: value
        for attr, value in values.items()
        if value is not None and getattr(row, attr, None) is None
    }
    _apply_missing_fields(row, filtered, prefix="performance.", result=result)
    return result


def apply_activity_vo2_precise_backfill(activity: Activity, db: Session) -> HealthBackfillResult:
    """Fyll vo2_max_precise på aktivitet fra daglig GarminPerformanceMetric."""
    result = HealthBackfillResult()
    if activity.vo2_max_precise is not None or activity.start_time is None:
        return result

    activity_day = activity.start_time.date()
    perf = (
        db.query(GarminPerformanceMetric)
        .filter(
            func.date(GarminPerformanceMetric.date) == activity_day,
            GarminPerformanceMetric.vo2_max_precise.isnot(None),
        )
        .first()
    )
    if perf is None:
        return result

    activity.vo2_max_precise = float(perf.vo2_max_precise)
    result.changed = True
    result.fixes.append(f"activity.vo2_max_precise={activity.vo2_max_precise} fra daglig performance ({activity_day})")
    return result


def backfill_activity_vo2_precise_in_range(
    db: Session,
    start_date: date,
    end_date: date,
) -> int:
    """Fyll vo2_max_precise på aktiviteter i periode fra daglige performance-målinger."""
    activities = (
        db.query(Activity)
        .filter(
            Activity.vo2_max_precise.is_(None),
            Activity.start_time.isnot(None),
            func.date(Activity.start_time) >= start_date,
            func.date(Activity.start_time) <= end_date,
        )
        .all()
    )
    updated = 0
    for activity in activities:
        result = apply_activity_vo2_precise_backfill(activity, db)
        if result.changed:
            updated += 1
    if updated:
        db.commit()
    return updated


def apply_body_battery_field_backfill(row: BodyBattery) -> HealthBackfillResult:
    """
    Body Battery charged/drained krever wellness-tidsserie som ikke lagres i DB.

    Utled kun net_charge når charged/drained allerede finnes. Uten tidsserie i DB
    kan eksisterende rader ikke fylles uten ny Garmin-henting.
    """
    result = HealthBackfillResult()
    if (
        row.net_charge is None
        and row.body_battery_charged is not None
        and row.body_battery_drained is not None
    ):
        row.net_charge = float(row.body_battery_charged) - float(row.body_battery_drained)
        result.changed = True
        result.fixes.append(f"body_battery.net_charge={row.net_charge}")
    return result


def apply_training_readiness_score_backfill(
    db: Session,
    *,
    limit: Optional[int] = None,
) -> HealthBackfillResult:
    """Fyll activity.training_readiness_score fra lokal TrainingReadinessService per aktivitetsdag."""
    from .training_readiness_service import TrainingReadinessService

    result = HealthBackfillResult()
    service = TrainingReadinessService(db)
    day_cache: Dict[date, Optional[float]] = {}
    skipped_days: Set[date] = set()
    processed_days: Set[date] = set()

    query = (
        db.query(Activity)
        .filter(
            Activity.start_time.isnot(None),
            Activity.training_readiness_score.is_(None),
        )
        .order_by(Activity.start_time.desc())
    )
    if limit is not None:
        query = query.limit(limit)

    for activity in query.all():
        activity_day = activity.start_time.date()
        if activity_day in processed_days:
            continue
        processed_days.add(activity_day)

        if activity_day not in day_cache and activity_day not in skipped_days:
            readiness = service.calculate_training_readiness(activity_day)
            total = readiness.get("total_score") if isinstance(readiness, dict) else None
            if (
                total is None
                or readiness.get("error")
                or not is_robust_training_readiness(readiness)
            ):
                day_cache[activity_day] = None
                skipped_days.add(activity_day)
            else:
                day_cache[activity_day] = float(total)

        score = day_cache.get(activity_day)
        if score is None:
            continue

        day_activities = db.query(Activity).filter(
            func.date(Activity.start_time) == activity_day,
            Activity.training_readiness_score.is_(None),
        ).all()
        for row in day_activities:
            row.training_readiness_score = round(score, 1)
            result.changed = True
            result.fixes.append(
                f"activity.training_readiness_score={row.training_readiness_score} "
                f"for {activity_day} (activity_id={row.activity_id})"
            )

    if skipped_days:
        result.fixes.append(f"readiness_days_skipped={len(skipped_days)}")
    return result


def run_health_metric_backfill(
    db: Session,
    *,
    sleep: bool = True,
    performance: bool = True,
    activities: bool = True,
    readiness: bool = True,
    body_battery: bool = True,
    limit: Optional[int] = None,
    dry_run: bool = False,
) -> HealthBackfillSummary:
    summary = HealthBackfillSummary()

    if sleep:
        query = db.query(Sleep).order_by(Sleep.sleep_date.desc())
        if limit is not None:
            query = query.limit(limit)
        for row in query.all():
            result = apply_sleep_field_backfill(row)
            if not result.changed:
                continue
            summary.sleep_rows_updated += 1
            for fix in result.fixes:
                field_name = fix.split("=", 1)[0].replace("sleep.", "sleep.")
                summary.field_counts[field_name] = summary.field_counts.get(field_name, 0) + 1
            if len(summary.examples) < 5:
                summary.examples.append(
                    {
                        "type": "sleep",
                        "date": row.sleep_date.isoformat() if row.sleep_date else None,
                        "fixes": result.fixes,
                    }
                )

    if performance:
        query = db.query(GarminPerformanceMetric).order_by(GarminPerformanceMetric.date.desc())
        if limit is not None:
            query = query.limit(limit)
        for row in query.all():
            result = apply_garmin_performance_field_backfill(row)
            if not result.changed:
                continue
            summary.performance_rows_updated += 1
            for fix in result.fixes:
                field_name = fix.split("=", 1)[0]
                summary.field_counts[field_name] = summary.field_counts.get(field_name, 0) + 1
            if len(summary.examples) < 8:
                summary.examples.append(
                    {
                        "type": "performance",
                        "date": row.date.date().isoformat() if isinstance(row.date, datetime) else str(row.date),
                        "fixes": result.fixes,
                    }
                )

    if activities:
        query = (
            db.query(Activity)
            .filter(Activity.vo2_max_precise.is_(None), Activity.start_time.isnot(None))
            .order_by(Activity.start_time.desc())
        )
        if limit is not None:
            query = query.limit(limit)
        for activity in query.all():
            result = apply_activity_vo2_precise_backfill(activity, db)
            if not result.changed:
                continue
            summary.activity_rows_updated += 1
            summary.field_counts["activity.vo2_max_precise"] = (
                summary.field_counts.get("activity.vo2_max_precise", 0) + 1
            )
            if len(summary.examples) < 12:
                summary.examples.append(
                    {
                        "type": "activity",
                        "activity_id": str(activity.activity_id),
                        "date": activity.start_time.date().isoformat() if activity.start_time else None,
                        "fixes": result.fixes,
                    }
                )

    if readiness:
        readiness_result = apply_training_readiness_score_backfill(db, limit=limit)
        skipped_marker = next(
            (fix for fix in readiness_result.fixes if fix.startswith("readiness_days_skipped=")),
            None,
        )
        if skipped_marker:
            summary.readiness_days_skipped = int(skipped_marker.split("=", 1)[1])
        activity_fixes = [
            fix for fix in readiness_result.fixes if fix.startswith("activity.training_readiness_score=")
        ]
        if activity_fixes:
            readiness_days = {
                fix.split("for ", 1)[1].split(" ", 1)[0]
                for fix in activity_fixes
                if "for " in fix
            }
            summary.readiness_days_updated = len(readiness_days)
            summary.activity_rows_updated += len(activity_fixes)
            summary.field_counts["activity.training_readiness_score"] = len(activity_fixes)
            if len(summary.examples) < 16:
                summary.examples.append(
                    {
                        "type": "readiness",
                        "days_updated": summary.readiness_days_updated,
                        "fixes": readiness_result.fixes[:5],
                    }
                )

    if body_battery:
        query = db.query(BodyBattery).order_by(BodyBattery.date.desc())
        if limit is not None:
            query = query.limit(limit)
        for row in query.all():
            result = apply_body_battery_field_backfill(row)
            if not result.changed:
                continue
            summary.body_battery_rows_updated += 1
            for fix in result.fixes:
                field_name = fix.split("=", 1)[0]
                summary.field_counts[field_name] = summary.field_counts.get(field_name, 0) + 1

    if dry_run:
        db.rollback()
    else:
        db.commit()

    return summary
