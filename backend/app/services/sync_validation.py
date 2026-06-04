"""Valideringsrapport etter synkronisering."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..database.models.activity import Activity
from ..database.models.sleep import HRV
from ..storage import DataStorage


def _activity_has_fit(storage: DataStorage, activity_id: str) -> bool:
    try:
        details = storage.get_activity_details(int(activity_id))
        return details is not None and not details.empty
    except Exception:
        return False


def _activity_has_hrv(db: Session, activity: Activity) -> bool:
    if activity.start_time is None:
        return False
    day = activity.start_time.date()
    return (
        db.query(HRV.id)
        .filter(HRV.measurement_date == day)
        .first()
        is not None
    )


def build_sync_validation_report(
    db: Session,
    storage: DataStorage,
    start_date: datetime,
    end_date: datetime,
    activity_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Bygg kort kvalitetsrapport for økter i synkperioden."""
    if start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=timezone.utc)
    if end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=timezone.utc)

    query = db.query(Activity).filter(
        Activity.start_time >= start_date,
        Activity.start_time <= end_date,
    )
    if activity_ids:
        query = query.filter(Activity.activity_id.in_(activity_ids))
    activities = query.order_by(Activity.start_time.desc()).all()

    rows: List[Dict[str, Any]] = []
    with_fit = 0
    with_fatigue = 0
    with_decoupling = 0
    with_hrv = 0

    for act in activities:
        aid = str(act.activity_id)
        has_fit = _activity_has_fit(storage, aid)
        has_fatigue = act.fatigue_resistance_score is not None
        has_decoupling = act.decoupling_percent is not None
        has_hrv = _activity_has_hrv(db, act)

        if has_fit:
            with_fit += 1
        if has_fatigue:
            with_fatigue += 1
        if has_decoupling:
            with_decoupling += 1
        if has_hrv:
            with_hrv += 1

        rows.append(
            {
                "activity_id": aid,
                "name": act.activity_name,
                "date": act.start_time.date().isoformat() if act.start_time else None,
                "has_fit": has_fit,
                "has_fatigue": has_fatigue,
                "has_decoupling": has_decoupling,
                "has_hrv": has_hrv,
            }
        )

    total = len(activities)
    return {
        "total_activities": total,
        "with_fit": with_fit,
        "with_fatigue": with_fatigue,
        "with_decoupling": with_decoupling,
        "with_hrv": with_hrv,
        "summary_text": (
            f"{total} økt(er): {with_fit} med FIT, {with_fatigue} med fatigue, "
            f"{with_decoupling} med decoupling, {with_hrv} med HRV på øktdato"
        ),
        "activities": rows,
    }
