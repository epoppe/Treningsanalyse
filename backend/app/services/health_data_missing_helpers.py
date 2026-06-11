from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from ..database.models.health_data_missing import HealthDataMissing


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
