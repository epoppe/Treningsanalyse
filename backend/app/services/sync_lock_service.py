"""Database-basert synk-lås — umulig å kjøre to synker samtidig."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from ..database.models.sync_lock import SyncLock

logger = logging.getLogger(__name__)

# Én global lås for alle Garmin-synker
GLOBAL_SYNC_LOCK = "garmin_sync"
DEFAULT_LOCK_TTL_SECONDS = 3600


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def try_acquire_lock(
    db: Session,
    lock_name: str,
    owner: str,
    *,
    ttl_seconds: int = DEFAULT_LOCK_TTL_SECONDS,
) -> bool:
    """Forsøk å ta lås. Returnerer True ved suksess.

    Utløpte låser overtas. Samme owner kan fornye egen lås.
    """
    now = _utcnow()
    expires = now + timedelta(seconds=ttl_seconds)
    row = db.query(SyncLock).filter_by(lock_name=lock_name).first()

    if row is None:
        db.add(
            SyncLock(
                lock_name=lock_name,
                owner=owner,
                heartbeat=now,
                expires=expires,
            )
        )
        db.commit()
        logger.info("Sync-lås '%s' tatt av %s", lock_name, owner)
        return True

    row_expires = _as_aware(row.expires)
    if row.owner == owner or (row_expires is not None and row_expires <= now):
        previous = row.owner
        row.owner = owner
        row.heartbeat = now
        row.expires = expires
        db.commit()
        if previous != owner:
            logger.info(
                "Sync-lås '%s' overtatt av %s (forrige=%s, utløpt=%s)",
                lock_name,
                owner,
                previous,
                row_expires is not None and row_expires <= now,
            )
        return True

    logger.info(
        "Sync-lås '%s' opptatt av %s (expires=%s)",
        lock_name,
        row.owner,
        row.expires,
    )
    return False


def heartbeat_lock(
    db: Session,
    lock_name: str,
    owner: str,
    *,
    ttl_seconds: int = DEFAULT_LOCK_TTL_SECONDS,
) -> bool:
    """Forny heartbeat hvis caller eier låsen."""
    now = _utcnow()
    row = db.query(SyncLock).filter_by(lock_name=lock_name, owner=owner).first()
    if row is None:
        return False
    row.heartbeat = now
    row.expires = now + timedelta(seconds=ttl_seconds)
    db.commit()
    return True


def release_lock(db: Session, lock_name: str, owner: str) -> bool:
    """Frigi lås hvis eid av owner. Returnerer True hvis frigitt."""
    row = db.query(SyncLock).filter_by(lock_name=lock_name, owner=owner).first()
    if row is None:
        return False
    db.delete(row)
    db.commit()
    logger.info("Sync-lås '%s' frigitt av %s", lock_name, owner)
    return True


def get_lock(db: Session, lock_name: str = GLOBAL_SYNC_LOCK) -> Optional[SyncLock]:
    return db.query(SyncLock).filter_by(lock_name=lock_name).first()


def is_locked(db: Session, lock_name: str = GLOBAL_SYNC_LOCK) -> bool:
    row = get_lock(db, lock_name)
    if row is None:
        return False
    expires = _as_aware(row.expires)
    return expires is not None and expires > _utcnow()


def cleanup_stale_sync_lock(db: Session, lock_name: str = GLOBAL_SYNC_LOCK) -> bool:
    """Frigir utløpt lås eller lås uten aktiv jobb-eier. Returnerer True hvis lås ble fjernet."""
    row = get_lock(db, lock_name)
    if row is None:
        return False

    expires = _as_aware(row.expires)
    now = _utcnow()
    if expires is not None and expires <= now:
        db.delete(row)
        db.commit()
        logger.info("Sync-lås '%s' fjernet (utløpt, owner=%s)", lock_name, row.owner)
        return True

    try:
        from .sync_job_store import ACTIVE_JOB_STATUSES, get_job

        holder = get_job(row.owner)
        if holder is None or holder.get("status") not in ACTIVE_JOB_STATUSES:
            owner = row.owner
            db.delete(row)
            db.commit()
            logger.info(
                "Sync-lås '%s' fjernet (ingen aktiv jobb for owner=%s, status=%s)",
                lock_name,
                owner,
                holder.get("status") if holder else "missing",
            )
            return True
    except Exception as exc:
        logger.warning("Kunne ikke vurdere stale sync-lås '%s': %s", lock_name, exc)

    return False
