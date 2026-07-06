"""Hjelpefunksjoner for å løse detaljert VO2 max på aktiviteter."""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database.models.activity import Activity, GarminPerformanceMetric


def build_vo2_max_precise_lookup(db: Session, activities: List[Activity]) -> Dict[date, float]:
    """Batch-oppslag av vo2_max_precise fra daglige GarminPerformanceMetric."""
    dates_needed = set()
    for activity in activities:
        if activity.vo2_max_precise is not None and activity.vo2_max_precise > 0:
            continue
        if activity.start_time is not None:
            dates_needed.add(activity.start_time.date())

    if not dates_needed:
        return {}

    rows = (
        db.query(func.date(GarminPerformanceMetric.date), GarminPerformanceMetric.vo2_max_precise)
        .filter(
            func.date(GarminPerformanceMetric.date).in_(list(dates_needed)),
            GarminPerformanceMetric.vo2_max_precise.isnot(None),
            GarminPerformanceMetric.vo2_max_precise > 0,
        )
        .all()
    )
    lookup: Dict[date, float] = {}
    for row_date, value in rows:
        if value is None:
            continue
        if isinstance(row_date, str):
            row_date = date.fromisoformat(row_date)
        lookup[row_date] = float(value)
    return lookup


def resolve_vo2_max_precise(activity: Activity, lookup: Dict[date, float]) -> Optional[float]:
    """Returnerer presis VO2 max fra aktivitet eller daglig performance-fallback."""
    if activity.vo2_max_precise is not None and activity.vo2_max_precise > 0:
        return float(activity.vo2_max_precise)
    if activity.start_time is not None:
        return lookup.get(activity.start_time.date())
    return None
