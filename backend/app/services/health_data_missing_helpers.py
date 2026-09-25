from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from ..database.models.health_data_missing import HealthDataMissing


def missing_dates_to_fetch(
    start: date,
    end: date,
    existing: set[date],
    known_missing: set[date],
) -> list[date]:
    """Dates in the range with no stored row and no known-empty marker.

    A date already recorded in HealthDataMissing is not fetched again by the
    range endpoints. Recent retries stay in the sync services, which have an
    explicit force-refresh flag.
    """
    if end < start:
        return []
    current = start
    pending: list[date] = []
    while current <= end:
        if current not in existing and current not in known_missing:
            pending.append(current)
        current += timedelta(days=1)
    return pending


def should_retry_health_data_missing(is_recent: bool, force_refresh_recent: bool) -> bool:
    """Nylige manglende helsedager kan prøves på nytt ved force refresh."""
    return force_refresh_recent and is_recent


def clear_health_data_missing(db: Session, data_type: str, missing_date: date) -> int:
    """Fjerner manglende-markering når data er hentet inn senere."""
    deleted = (
        db.query(HealthDataMissing)
        .filter_by(data_type=data_type, missing_date=missing_date)
        .delete()
    )
    if deleted:
        db.flush()
    return deleted
