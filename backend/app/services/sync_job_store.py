"""Minne + database-lagring for synkroniseringsjobber."""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, FrozenSet, Iterator, Optional, Set, Tuple

from ..database.session import SessionLocal

logger = logging.getLogger(__name__)

ACTIVE_JOB_STATUSES = frozenset({"queued", "processing"})

_job_slot_lock = threading.RLock()


class PersistedSyncJobs(dict):
    """Dict-lignende jobblager som persisterer til SQLite ved endring."""

    def _persist(self, job_id: str) -> None:
        if job_id not in self:
            return
        try:
            from ..database.models.sync_job import SyncJob

            payload = self[job_id]
            db = SessionLocal()
            try:
                row = db.query(SyncJob).filter_by(job_id=job_id).first()
                if row is None:
                    row = SyncJob(job_id=job_id, job_type=payload.get("job_type", "unknown"))
                    db.add(row)
                row.job_type = payload.get("job_type", row.job_type)
                row.status = payload.get("status", row.status)
                row.message = payload.get("message")
                row.error = payload.get("error")
                row.progress = payload.get("progress")
                row.result = payload.get("result")
                row.start_time = payload.get("start_time")
                row.end_time = payload.get("end_time")
                if payload.get("created_at") and row.created_at is None:
                    row.created_at = payload.get("created_at")
                db.commit()
            finally:
                db.close()
        except Exception as exc:
            logger.warning("Kunne ikke persistere synk-jobb %s: %s", job_id, exc)

    def __setitem__(self, key: str, value: Dict[str, Any]) -> None:
        super().__setitem__(key, value)
        self._persist(key)

    def update(self, *args: Any, **kwargs: Any) -> None:
        super().update(*args, **kwargs)
        keys = set()
        if args and isinstance(args[0], dict):
            keys.update(args[0].keys())
        keys.update(kwargs.keys())
        for job_id in keys:
            if job_id in self:
                self._persist(job_id)


_store: Optional[PersistedSyncJobs] = None


def get_sync_jobs_store() -> PersistedSyncJobs:
    global _store
    if _store is None:
        _store = PersistedSyncJobs()
        _hydrate_from_database(_store)
    return _store


def _hydrate_from_database(store: PersistedSyncJobs) -> None:
    """Last inn aktive jobber fra DB ved oppstart (overlever backend-restart)."""
    try:
        from ..database.models.sync_job import SyncJob

        db = SessionLocal()
        try:
            rows = (
                db.query(SyncJob)
                .filter(SyncJob.status.in_(list(ACTIVE_JOB_STATUSES)))
                .order_by(SyncJob.created_at.desc())
                .limit(20)
                .all()
            )
            for row in rows:
                store[row.job_id] = {
                    "status": row.status,
                    "message": row.message,
                    "job_type": row.job_type,
                    "created_at": row.created_at,
                    "start_time": row.start_time,
                    "end_time": row.end_time,
                    "progress": row.progress,
                    "result": row.result,
                    "error": row.error,
                }
            if rows:
                logger.info("Gjenopprettet %s aktive synk-jobber fra database", len(rows))
        finally:
            db.close()
    except Exception as exc:
        logger.debug("Hydrering av synk-jobber hoppet over: %s", exc)


def _new_job_payload(job_type: str, message: str) -> Dict[str, Any]:
    return {
        "status": "queued",
        "message": message,
        "job_type": job_type,
        "created_at": datetime.now(timezone.utc),
        "start_time": None,
        "end_time": None,
        "progress": None,
    }


def find_active_job_by_types(job_types: Set[str]) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Finn nyeste aktiv jobb for ett av job_type-verdiene."""
    for existing_job_id, job in iter_jobs_reversed():
        if job.get("job_type") in job_types and job.get("status") in ACTIVE_JOB_STATUSES:
            return existing_job_id, job
    return None


def acquire_job_slot(
    job_type: str,
    message: str = "Queued",
    *,
    shared_job_types: Optional[FrozenSet[str]] = None,
) -> Tuple[str, Dict[str, Any], bool]:
    """Atomisk deduplisering: returner aktiv jobb eller opprett ny.

    Returns:
        (job_id, job_dict, reused_existing)
    """
    with _job_slot_lock:
        types_to_check = {job_type}
        if shared_job_types:
            types_to_check |= set(shared_job_types)

        active = find_active_job_by_types(types_to_check)
        if active is not None:
            return active[0], active[1], True

        store = get_sync_jobs_store()
        job_id = str(uuid.uuid4())
        store[job_id] = _new_job_payload(job_type, message)
        return job_id, store[job_id], False


def create_job(job_type: str, message: str = "Queued") -> str:
    """Opprett ny jobb uten deduplisering (bruk acquire_job_slot for trygg start)."""
    store = get_sync_jobs_store()
    job_id = str(uuid.uuid4())
    store[job_id] = _new_job_payload(job_type, message)
    return job_id


def reset_sync_jobs_store_for_tests() -> None:
    """Tøm in-memory jobblager (kun for tester)."""
    global _store
    with _job_slot_lock:
        if _store is not None:
            _store.clear()
        _store = None
        try:
            from ..database.models.sync_job import SyncJob

            db = SessionLocal()
            try:
                db.query(SyncJob).delete()
                db.commit()
            finally:
                db.close()
        except Exception as exc:
            logger.debug("Kunne ikke tømme sync_job-tabell i test-reset: %s", exc)


def set_job_phase(
    job_id: str,
    phase_index: int,
    total_phases: int,
    message: str,
    *,
    sub_current: Optional[int] = None,
    sub_total: Optional[int] = None,
) -> None:
    store = get_sync_jobs_store()
    if job_id not in store:
        return
    percent = int((phase_index / total_phases) * 100) if total_phases > 0 else 0
    progress: Dict[str, Any] = {
        "phase": phase_index + 1,
        "total_phases": total_phases,
        "percent": min(percent, 99),
        "label": message,
    }
    if sub_current is not None and sub_total is not None and sub_total > 0:
        progress["sub_current"] = sub_current
        progress["sub_total"] = sub_total
        progress["sub_label"] = f"{sub_current}/{sub_total}"
    store[job_id]["progress"] = progress
    store[job_id]["message"] = message
    store._persist(job_id)


def mark_job_processing(job_id: str, message: Optional[str] = None) -> None:
    store = get_sync_jobs_store()
    if job_id not in store:
        return
    store[job_id]["status"] = "processing"
    store[job_id]["start_time"] = datetime.now(timezone.utc)
    if message:
        store[job_id]["message"] = message
    store._persist(job_id)


def load_job_from_db(job_id: str) -> Optional[Dict[str, Any]]:
    try:
        from ..database.models.sync_job import SyncJob

        db = SessionLocal()
        try:
            row = db.query(SyncJob).filter_by(job_id=job_id).first()
            if row is None:
                return None
            return {
                "status": row.status,
                "message": row.message,
                "job_type": row.job_type,
                "created_at": row.created_at,
                "start_time": row.start_time,
                "end_time": row.end_time,
                "progress": row.progress,
                "result": row.result,
                "error": row.error,
            }
        finally:
            db.close()
    except Exception:
        return None


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    store = get_sync_jobs_store()
    job = store.get(job_id)
    if job is not None:
        return job
    job = load_job_from_db(job_id)
    if job is not None:
        store[job_id] = job
    return job


def iter_jobs_reversed() -> Iterator[tuple[str, Dict[str, Any]]]:
    store = get_sync_jobs_store()
    yield from reversed(list(store.items()))
