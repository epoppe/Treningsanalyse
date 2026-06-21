"""Hjelpefunksjoner for å avgrense løpeaktiviteter."""
from __future__ import annotations

from typing import FrozenSet, Optional

from sqlalchemy.orm import Query

from ..database.models.activity import Activity, ActivityType

# Eksplisitt hviteliste — unngår f.eks. langrenn, sykling og «running» i andre type_key.
RUNNING_TYPE_KEYS: FrozenSet[str] = frozenset(
    {
        "running",
        "trail_running",
        "street_running",
        "track_running",
    }
)

TREADMILL_TYPE_KEYS: FrozenSet[str] = frozenset(
    {
        "treadmill_running",
        "indoor_running",
    }
)

# Aktivitetstyper der FIT ikke skal lastes ned (innendørs / tredemølle).
INDOOR_ACTIVITY_TYPE_KEYS: FrozenSet[str] = frozenset(
    {
        *TREADMILL_TYPE_KEYS,
        "indoor_cycling",
        "indoor_cardio",
    }
)


def is_indoor_type_key(type_key: Optional[str]) -> bool:
    if not type_key:
        return False
    key = type_key.lower()
    if key in INDOOR_ACTIVITY_TYPE_KEYS:
        return True
    return key.startswith("indoor_")


def is_indoor_activity(activity: Optional[Activity]) -> bool:
    if activity is None or activity.activity_type is None:
        return False
    return is_indoor_type_key(activity.activity_type.type_key)


def should_download_fit(activity: Optional[Activity]) -> bool:
    """FIT-nedlasting er kun relevant for utendørsaktiviteter med GPS/rute."""
    return not is_indoor_activity(activity)


def is_running_activity(
    activity: Optional[Activity],
    *,
    include_treadmill: bool = False,
) -> bool:
    if activity is None or activity.activity_type is None:
        return False
    type_key = activity.activity_type.type_key or ""
    if type_key in RUNNING_TYPE_KEYS:
        return True
    return include_treadmill and type_key in TREADMILL_TYPE_KEYS


def running_type_keys_for_query(*, include_treadmill: bool = False) -> FrozenSet[str]:
    if include_treadmill:
        return RUNNING_TYPE_KEYS | TREADMILL_TYPE_KEYS
    return RUNNING_TYPE_KEYS


def apply_running_activity_filter(query: Query, *, include_treadmill: bool = False) -> Query:
    """Begrens SQLAlchemy-query til løpeaktiviteter."""
    return query.join(Activity.activity_type).filter(
        ActivityType.type_key.in_(running_type_keys_for_query(include_treadmill=include_treadmill))
    )
