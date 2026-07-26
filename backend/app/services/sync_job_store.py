"""Minne + database-lagring for synkroniseringsjobber.

Integrerer SyncRun (audit/statistikk) og SyncLock (eksklusiv synk).
"""

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


class JobRecord(dict):
    """Jobb-dict som persisterer og oppdaterer SyncRun/lock ved endring."""

    def __init__(self, store: "PersistedSyncJobs", job_id: str, data: Optional[Dict[str, Any]] = None):
        super().__init__(data or {})
        self._store = store
        self._job_id = job_id

    def update(self, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        previous_status = self.get("status")
        super().update(*args, **kwargs)
        self._store._after_job_change(self._job_id, self, previous_status=previous_status)

    def __setitem__(self, key: str, value: Any) -> None:
        previous_status = self.get("status")
        super().__setitem__(key, value)
        self._store._after_job_change(self._job_id, self, previous_status=previous_status)


class PersistedSyncJobs(dict):
    """Dict-lignende jobblager som persisterer til SQLite ved endring."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._suppress_side_effects = False

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

    def _ensure_job_record(self, job_id: str, value: Dict[str, Any]) -> JobRecord:
        if isinstance(value, JobRecord):
            return value
        return JobRecord(self, job_id, value)

    def __setitem__(self, key: str, value: Dict[str, Any]) -> None:
        record = self._ensure_job_record(key, value)
        previous_status = None
        if key in self:
            previous_status = self[key].get("status")
        super().__setitem__(key, record)
        self._after_job_change(key, record, previous_status=previous_status)

    def __getitem__(self, key: str) -> JobRecord:
        value = super().__getitem__(key)
        if not isinstance(value, JobRecord):
            record = JobRecord(self, key, value)
            super().__setitem__(key, record)
            return record
        return value

    def get(self, key: str, default: Any = None) -> Any:
        if key not in self:
            return default
        return self[key]

    def update(self, *args: Any, **kwargs: Any) -> None:
        if args and isinstance(args[0], dict):
            for job_id, payload in args[0].items():
                self[job_id] = payload
        for job_id, payload in kwargs.items():
            self[job_id] = payload

    def _after_job_change(
        self,
        job_id: str,
        payload: Dict[str, Any],
        *,
        previous_status: Optional[str],
    ) -> None:
        if self._suppress_side_effects:
            return
        self._persist(job_id)
        status = payload.get("status")
        if status == previous_status:
            return

        if status == "processing" and previous_status != "processing":
            self._start_sync_run(job_id, payload)
        elif status in {"completed", "failed"} and previous_status not in {"completed", "failed"}:
            self._finish_sync_run(job_id, payload, status=status)
            self._release_sync_lock(job_id)

    def _start_sync_run(self, job_id: str, payload: Dict[str, Any]) -> None:
        if payload.get("sync_run_id") is not None:
            return
        try:
            from .sync_run_service import start_run_for_job

            run_id = start_run_for_job(job_id, payload.get("job_type", "unknown"))
            if run_id is not None:
                # Unngå rekursiv status-trigger: skriv direkte på dict
                dict.__setitem__(payload, "sync_run_id", run_id)
                self._persist(job_id)
        except Exception as exc:
            logger.warning("SyncRun-start feilet for %s: %s", job_id, exc)

    def _finish_sync_run(self, job_id: str, payload: Dict[str, Any], *, status: str) -> None:
        run_id = payload.get("sync_run_id")
        try:
            from .sync_run_service import finish_run_for_job

            finish_run_for_job(
                run_id,
                status=status,
                result=payload.get("result"),
                error=payload.get("error"),
            )
        except Exception as exc:
            logger.warning("SyncRun-avslutning feilet for %s: %s", job_id, exc)

    def _release_sync_lock(self, job_id: str) -> None:
        try:
            from .sync_lock_service import GLOBAL_SYNC_LOCK, release_lock

            db = SessionLocal()
            try:
                release_lock(db, GLOBAL_SYNC_LOCK, job_id)
            finally:
                db.close()
        except Exception as exc:
            logger.warning("Kunne ikke frigi sync-lås for %s: %s", job_id, exc)


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
        from .sync_lock_service import GLOBAL_SYNC_LOCK, get_lock, _as_aware, _utcnow

        db = SessionLocal()
        try:
            # Marker stuck jobber uten gyldig lås som failed (restartbart utgangspunkt)
            lock = get_lock(db, GLOBAL_SYNC_LOCK)
            lock_owner = None
            if lock is not None:
                expires = _as_aware(lock.expires)
                lock_valid = expires is not None and expires > _utcnow()
                lock_owner = lock.owner if lock_valid else None

            rows = (
                db.query(SyncJob)
                .filter(SyncJob.status.in_(list(ACTIVE_JOB_STATUSES)))
                .order_by(SyncJob.created_at.desc())
                .limit(20)
                .all()
            )
            store._suppress_side_effects = True
            try:
                for row in rows:
                    if lock_owner and row.job_id == lock_owner:
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
                    else:
                        # Stuck uten lås — marker failed så ny synk kan starte
                        row.status = "failed"
                        row.error = row.error or "Jobb markert failed ved oppstart (mangler gyldig sync-lås)"
                        row.end_time = datetime.now(timezone.utc)
                        db.commit()
                        logger.warning(
                            "Synk-jobb %s (%s) markert failed ved hydrering — klar for restart",
                            row.job_id,
                            row.job_type,
                        )
            finally:
                store._suppress_side_effects = False
            if rows:
                logger.info("Hydrerte synk-jobber fra database (%s aktive rader sjekket)", len(rows))
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
        "sync_run_id": None,
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
    acquire_sync_lock: bool = True,
) -> Tuple[str, Dict[str, Any], bool]:
    """Atomisk deduplisering + valgfri global sync-lås.

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

        # Global sync-lås: umulig å kjøre to synker samtidig (på tvers av job_type)
        if acquire_sync_lock:
            from .sync_lock_service import GLOBAL_SYNC_LOCK, try_acquire_lock, get_lock

            db = SessionLocal()
            try:
                provisional_id = str(uuid.uuid4())
                if not try_acquire_lock(db, GLOBAL_SYNC_LOCK, provisional_id):
                    lock = get_lock(db, GLOBAL_SYNC_LOCK)
                    if lock is not None:
                        holder = get_job(lock.owner)
                        if holder is not None and holder.get("status") in ACTIVE_JOB_STATUSES:
                            return lock.owner, holder, True
                    owner = lock.owner if lock else "ukjent"
                    raise RuntimeError(f"Synk-lås opptatt av {owner} — prøv igjen senere")

                store = get_sync_jobs_store()
                store[provisional_id] = _new_job_payload(job_type, message)
                return provisional_id, store[provisional_id], False
            finally:
                db.close()

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
            from ..database.models.sync_run import SyncRun
            from ..database.models.sync_lock import SyncLock

            db = SessionLocal()
            try:
                db.query(SyncJob).delete()
                db.query(SyncRun).delete()
                db.query(SyncLock).delete()
                db.commit()
            finally:
                db.close()
        except Exception as exc:
            logger.debug("Kunne ikke tømme sync-tabeller i test-reset: %s", exc)


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
    # Oppdater uten å trigge status-overgang
    job = store[job_id]
    dict.__setitem__(job, "progress", progress)
    dict.__setitem__(job, "message", message)
    store._persist(job_id)


def mark_job_processing(job_id: str, message: Optional[str] = None) -> None:
    store = get_sync_jobs_store()
    if job_id not in store:
        return
    updates: Dict[str, Any] = {
        "status": "processing",
        "start_time": datetime.now(timezone.utc),
    }
    if message:
        updates["message"] = message
    store[job_id].update(updates)


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
