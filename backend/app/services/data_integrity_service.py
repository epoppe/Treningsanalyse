"""Automatisk dataintegritetskontroll for aktiviteter.

Sjekker blant annet manglende datoer, ugyldig pace, negative distanser,
null HR, manglende VO2 og duplikater. Resultatet eksponeres via /health/data.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database.models.activity import Activity, ActivityType

logger = logging.getLogger(__name__)

# Heuristikk for plausibel løpepace (sekunder per km)
_MIN_PACE_SEC_PER_KM = 90.0
_MAX_PACE_SEC_PER_KM = 3600.0

# Løpe-lignende type_keys (for VO2-forventning) — inklusiv, ikke streng
_RUNNING_HINTS = ("run", "trail", "track", "treadmill", "virtual_run")


def _is_running_type(type_key: Optional[str]) -> bool:
    if not type_key:
        return False
    key = type_key.lower()
    return any(hint in key for hint in _RUNNING_HINTS)


def build_data_integrity_report(db: Session, *, sample_limit: int = 20) -> Dict[str, Any]:
    """Kjør integritetskontroller og returner komprimert rapport."""
    issues: Dict[str, Dict[str, Any]] = {}

    total = db.query(func.count(Activity.activity_id)).scalar() or 0

    # 1) Manglende datoer
    missing_dates_q = db.query(Activity.activity_id).filter(Activity.start_time.is_(None))
    issues["missing_dates"] = {
        "count": missing_dates_q.count(),
        "sample_ids": [r[0] for r in missing_dates_q.limit(sample_limit).all()],
    }

    # 2) Negative distanser
    negative_distance_q = db.query(Activity.activity_id).filter(
        Activity.distance.isnot(None),
        Activity.distance < 0,
    )
    issues["negative_distances"] = {
        "count": negative_distance_q.count(),
        "sample_ids": [r[0] for r in negative_distance_q.limit(sample_limit).all()],
    }

    # 3) Ugyldige pace-verdier
    invalid_pace_q = db.query(Activity.activity_id).filter(
        Activity.average_pace.isnot(None),
        ((Activity.average_pace < _MIN_PACE_SEC_PER_KM) | (Activity.average_pace > _MAX_PACE_SEC_PER_KM)),
    )
    issues["invalid_pace"] = {
        "count": invalid_pace_q.count(),
        "sample_ids": [r[0] for r in invalid_pace_q.limit(sample_limit).all()],
        "valid_range_sec_per_km": [_MIN_PACE_SEC_PER_KM, _MAX_PACE_SEC_PER_KM],
    }

    # 4) Null HR på aktiviteter med distanse
    null_hr_q = db.query(Activity.activity_id).filter(
        Activity.distance.isnot(None),
        Activity.distance > 0,
        Activity.average_heart_rate.is_(None),
    )
    issues["null_hr"] = {
        "count": null_hr_q.count(),
        "sample_ids": [r[0] for r in null_hr_q.limit(sample_limit).all()],
        "note": "Aktiviteter med distanse>0 uten average_heart_rate",
    }

    # 5) Manglende VO2 på løpeaktiviteter ≥1 km
    running_missing: List[str] = []
    for activity_id, type_key in (
        db.query(Activity.activity_id, ActivityType.type_key)
        .outerjoin(ActivityType, Activity.activity_type_id == ActivityType.id)
        .filter(
            Activity.distance.isnot(None),
            Activity.distance >= 1000,
            Activity.vo2_max.is_(None),
            Activity.vo2_max_precise.is_(None),
        )
        .all()
    ):
        if _is_running_type(type_key):
            running_missing.append(activity_id)
    issues["missing_vo2"] = {
        "count": len(running_missing),
        "sample_ids": running_missing[:sample_limit],
        "note": "Løpeaktiviteter ≥1 km uten vo2_max / vo2_max_precise",
    }

    # 6) Duplikater — samme start_time + distance + duration
    all_dup_groups = (
        db.query(
            Activity.start_time,
            Activity.distance,
            Activity.duration,
            func.count(Activity.activity_id).label("cnt"),
        )
        .filter(Activity.start_time.isnot(None))
        .group_by(Activity.start_time, Activity.distance, Activity.duration)
        .having(func.count(Activity.activity_id) > 1)
        .all()
    )
    duplicate_samples: List[Dict[str, Any]] = []
    for start_time, distance, duration, cnt in all_dup_groups[:sample_limit]:
        ids = [
            r[0]
            for r in db.query(Activity.activity_id)
            .filter(
                Activity.start_time == start_time,
                Activity.distance == distance,
                Activity.duration == duration,
            )
            .limit(10)
            .all()
        ]
        duplicate_samples.append(
            {
                "start_time": start_time.isoformat() if start_time else None,
                "distance": distance,
                "duration": duration,
                "count": int(cnt),
                "activity_ids": ids,
            }
        )
    issues["duplicates"] = {
        "group_count": len(all_dup_groups),
        "sample_groups": duplicate_samples,
        "note": "Grupper med samme start_time+distance+duration",
    }

    critical_total = (
        issues["missing_dates"]["count"]
        + issues["negative_distances"]["count"]
        + issues["invalid_pace"]["count"]
        + issues["duplicates"]["group_count"]
    )
    warning_total = issues["null_hr"]["count"] + issues["missing_vo2"]["count"]

    if critical_total > 0:
        status = "unhealthy"
    elif warning_total > 0:
        status = "degraded"
    else:
        status = "ok"

    return {
        "status": status,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "activity_count": int(total),
        "critical_issue_count": critical_total,
        "warning_issue_count": warning_total,
        "issues": issues,
    }
