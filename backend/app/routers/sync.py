from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel
from datetime import date, datetime, timezone, timedelta
import logging
from sqlalchemy.orm import Session
import pytz
import asyncio
from fastapi import status
import uuid
from typing import Dict, Optional, Any

from ..services.garmin_client import GarminClient
from ..storage import DataStorage
from ..services.sync_service import SyncService
from ..dependencies import get_garmin_client, get_data_storage, get_db
from ..database.session import SessionLocal
from ..database.models.activity import Activity
from garth.exc import GarthException
from ..config import settings
from ..services.hrv_service import HRVService
from ..services.body_battery_service import BodyBatteryService
from ..services.sync_job_store import (
    ACTIVE_JOB_STATUSES,
    create_job as _store_create_job,
    get_job as _store_get_job,
    get_sync_jobs_store,
    iter_jobs_reversed,
    mark_job_processing as _store_mark_job_processing,
    set_job_phase,
)
from ..services.sync_validation import build_sync_validation_report

logger = logging.getLogger(__name__)
router = APIRouter()

sync_jobs = get_sync_jobs_store()

NEW_ACTIVITIES_PHASES = 4
FULL_SYNC_PHASES = 4

# Synk som konkurrerer om samme aktivitetsspor — ikke kjør samtidig
ACTIVITY_QUEUE_JOB_TYPES = frozenset({"activities_sync", "new_activities_sync"})


def _create_job(job_type: str, message: str = "Queued") -> str:
    return _store_create_job(job_type, message)


def _find_active_job_by_type(job_type: str) -> Optional[tuple[str, Dict[str, Any]]]:
    for existing_job_id, job in iter_jobs_reversed():
        if job.get("job_type") == job_type and job.get("status") in ACTIVE_JOB_STATUSES:
            return existing_job_id, job
    return None


def _find_active_activity_queue_job() -> Optional[tuple[str, Dict[str, Any]]]:
    """Finn aktiv aktivitetssynk eller «nye aktiviteter»-jobb (samme kø)."""
    for existing_job_id, job in iter_jobs_reversed():
        if (
            job.get("job_type") in ACTIVITY_QUEUE_JOB_TYPES
            and job.get("status") in ACTIVE_JOB_STATUSES
        ):
            return existing_job_id, job
    return None


def _mark_job_processing(job_id: str, message: Optional[str] = None, phase: Optional[int] = None, total_phases: Optional[int] = None):
    _store_mark_job_processing(job_id, message)
    if phase is not None and total_phases is not None and message:
        set_job_phase(job_id, phase, total_phases, message)


def _completed_job_response(message: str, job_id: str) -> Dict[str, Any]:
    job = sync_jobs.get(job_id, {})
    return {
        "message": message,
        "job_id": job_id,
        "status": job.get("status", "queued"),
        "job_type": job.get("job_type"),
        "reused_existing_job": False,
    }


def _existing_job_response(message: str, job_id: str, job: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "message": message,
        "job_id": job_id,
        "status": job.get("status", "unknown"),
        "job_type": job.get("job_type"),
        "reused_existing_job": True,
    }

class SyncRequest(BaseModel):
    start_date: date
    end_date: date
    ignore_sync_state: Optional[bool] = False
    fit_download_mode: Optional[str] = "chunked"  # "auto" | "chunked"

async def run_activity_sync_with_fit_data(job_id: str, garmin_client: GarminClient, storage: DataStorage, start_date: datetime, end_date: datetime, force_refresh_recent: bool = False, fit_data_limit: int = 100, ignore_sync_state: bool = False, fit_download_mode: str = "chunked"):
    """Kjører aktivitetssynkronisering i bakgrunnen med automatisk FIT-data nedlasting."""
    db_session = None
    try:
        _mark_job_processing(job_id, "Synkroniserer aktiviteter med FIT-data...")
        db_session = SessionLocal()
        sync_service = SyncService(garmin_client, storage, db_session)
        result = await sync_service.sync_activities_with_fit_data(
            start_date,
            end_date,
            force_refresh_recent,
            fit_data_limit,
            ignore_sync_state,
            fit_download_mode,
        )
        sync_jobs[job_id].update({"status": "completed", "result": result, "end_time": datetime.now(timezone.utc)})
    except Exception as e:
        logger.critical(f"Feil i utvidet aktivitetssynk (jobb {job_id}): {e}", exc_info=True)
        sync_jobs[job_id].update({"status": "failed", "error": str(e), "end_time": datetime.now(timezone.utc)})
    finally:
        if db_session:
            db_session.close()

async def run_activity_sync(job_id: str, garmin_client: GarminClient, storage: DataStorage, start_date: datetime, end_date: datetime):
    """Kjører aktivitetssynkronisering i bakgrunnen."""
    db_session = None
    try:
        _mark_job_processing(job_id, "Synkroniserer aktiviteter...")
        db_session = SessionLocal()
        sync_service = SyncService(garmin_client, storage, db_session)
        result = await sync_service.sync_activities(start_date, end_date)
        sync_jobs[job_id].update({"status": "completed", "result": result, "end_time": datetime.now(timezone.utc)})
    except Exception as e:
        logger.critical(f"Feil i aktivitetssynk (jobb {job_id}): {e}", exc_info=True)
        sync_jobs[job_id].update({"status": "failed", "error": str(e), "end_time": datetime.now(timezone.utc)})
    finally:
        if db_session:
            db_session.close()

async def run_activity_sync_with_force(job_id: str, garmin_client: GarminClient, storage: DataStorage, start_date: datetime, end_date: datetime, force_refresh_recent: bool):
    """Kjører aktivitetssynkronisering i bakgrunnen med mulighet for force refresh av nylige data."""
    db_session = None
    try:
        _mark_job_processing(job_id, "Synkroniserer aktiviteter (force refresh)...")
        db_session = SessionLocal()
        sync_service = SyncService(garmin_client, storage, db_session)
        result = await sync_service.sync_activities(start_date, end_date, force_refresh_recent)
        sync_jobs[job_id].update({"status": "completed", "result": result, "end_time": datetime.now(timezone.utc)})
    except Exception as e:
        logger.critical(f"Feil i aktivitetssynk (jobb {job_id}): {e}", exc_info=True)
        sync_jobs[job_id].update({"status": "failed", "error": str(e), "end_time": datetime.now(timezone.utc)})
    finally:
        if db_session:
            db_session.close()

async def run_health_sync(job_id: str, garmin_client: GarminClient, storage: DataStorage, start_date: datetime, end_date: datetime):
    """Kjører helsedatasynkronisering i bakgrunnen."""
    db_session = None
    try:
        _mark_job_processing(job_id, "Synkroniserer helsedata...")
        db_session = SessionLocal()
        sync_service = SyncService(garmin_client, storage, db_session)
        await sync_service.sync_health_data(start_date, end_date)
        sync_jobs[job_id].update({"status": "completed", "result": "OK", "end_time": datetime.now(timezone.utc)})
    except Exception as e:
        logger.critical(f"Feil i helsesynk (jobb {job_id}): {e}", exc_info=True)
        sync_jobs[job_id].update({"status": "failed", "error": str(e), "end_time": datetime.now(timezone.utc)})
    finally:
        if db_session:
            db_session.close()

async def run_health_sync_with_force(job_id: str, garmin_client: GarminClient, storage: DataStorage, start_date: datetime, end_date: datetime, force_refresh_recent: bool):
    """Kjører helsedatasynkronisering i bakgrunnen med mulighet for force refresh av nylige data."""
    db_session = None
    try:
        _mark_job_processing(job_id, "Synkroniserer helsedata (force refresh)...")
        db_session = SessionLocal()
        sync_service = SyncService(garmin_client, storage, db_session)
        await sync_service.sync_health_data(start_date, end_date, force_refresh_recent)
        sync_jobs[job_id].update({"status": "completed", "result": "OK", "end_time": datetime.now(timezone.utc)})
    except Exception as e:
        logger.critical(f"Feil i helsesynk (jobb {job_id}): {e}", exc_info=True)
        sync_jobs[job_id].update({"status": "failed", "error": str(e), "end_time": datetime.now(timezone.utc)})
    finally:
        if db_session:
            db_session.close()

async def run_garmin_performance_metrics_sync(
    job_id: str,
    garmin_client: GarminClient,
    storage: DataStorage,
    start_date: datetime,
    end_date: datetime,
    force_refresh_recent: bool = False,
    ignore_sync_state: bool = False,
):
    """Kjører synk av dagsbaserte Garmin performance-metrikker i bakgrunnen."""
    db_session = None
    try:
        _mark_job_processing(job_id, "Synkroniserer Garmin performance metrics...")
        db_session = SessionLocal()
        sync_service = SyncService(garmin_client, storage, db_session)
        result = await sync_service.sync_garmin_performance_metrics(
            start_date,
            end_date,
            force_refresh_recent=force_refresh_recent,
            ignore_sync_state=ignore_sync_state,
        )
        sync_jobs[job_id].update({"status": "completed", "result": result, "end_time": datetime.now(timezone.utc)})
    except Exception as e:
        logger.critical(f"Feil i Garmin performance metrics-synk (jobb {job_id}): {e}", exc_info=True)
        sync_jobs[job_id].update({"status": "failed", "error": str(e), "end_time": datetime.now(timezone.utc)})
    finally:
        if db_session:
            db_session.close()

async def run_fit_data_download(job_id: str, garmin_client: GarminClient, storage: DataStorage, activity_ids: list = None, limit: int = None):
    """Kjører FIT-data nedlasting i bakgrunnen."""
    db_session = None
    try:
        _mark_job_processing(job_id, "Laster ned FIT-data...")
        db_session = SessionLocal()
        sync_service = SyncService(garmin_client, storage, db_session)
        result = await sync_service.download_fit_data_for_activities(activity_ids, limit)
        sync_jobs[job_id].update({"status": "completed", "result": result, "end_time": datetime.now(timezone.utc)})
    except Exception as e:
        logger.critical(f"Feil i FIT-data nedlasting (jobb {job_id}): {e}", exc_info=True)
        sync_jobs[job_id].update({"status": "failed", "error": str(e), "end_time": datetime.now(timezone.utc)})
    finally:
        if db_session:
            db_session.close()

async def run_training_effect_refresh(job_id: str, garmin_client: GarminClient, storage: DataStorage, force: bool = False):
    """Kjører Training Effect-henting for aktiviteter som mangler eller har 0."""
    db_session = None
    try:
        _mark_job_processing(job_id, "Synkroniserer Training Effect...")
        db_session = SessionLocal()
        sync_service = SyncService(garmin_client, storage, db_session)
        result = await sync_service.sync_training_effect_for_missing(force=force)
        sync_jobs[job_id].update({"status": "completed", "result": result, "end_time": datetime.now(timezone.utc)})
    except Exception as e:
        logger.critical(f"Feil i Training Effect refresh (jobb {job_id}): {e}", exc_info=True)
        sync_jobs[job_id].update({"status": "failed", "error": str(e), "end_time": datetime.now(timezone.utc)})
    finally:
        if db_session:
            db_session.close()

async def run_fit_data_download_period(job_id: str, garmin_client: GarminClient, storage: DataStorage, start_date: datetime, end_date: datetime):
    """Kjører FIT-data nedlasting for en periode i bakgrunnen."""
    db_session = None
    try:
        _mark_job_processing(job_id, "Laster ned FIT-data for periode...")
        db_session = SessionLocal()
        sync_service = SyncService(garmin_client, storage, db_session)
        result = await sync_service.download_fit_data_for_period(start_date, end_date)
        sync_jobs[job_id].update({"status": "completed", "result": result, "end_time": datetime.now(timezone.utc)})
    except Exception as e:
        logger.critical(f"Feil i FIT-data nedlasting for periode (jobb {job_id}): {e}", exc_info=True)
        sync_jobs[job_id].update({"status": "failed", "error": str(e), "end_time": datetime.now(timezone.utc)})
    finally:
        if db_session:
            db_session.close()

def _dt_to_iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _activity_ids_from_sync_result(activity_result: dict) -> list[str]:
    sync_part = activity_result.get("sync_result") or {}
    ids = list(sync_part.get("activity_ids") or [])
    return [str(aid) for aid in ids]


def _finalize_sync_job(
    job_id: str,
    combined_result: dict,
    db_session: Session,
    storage: DataStorage,
    start_date: datetime,
    end_date: datetime,
    activity_ids: Optional[list[str]] = None,
) -> None:
    validation = build_sync_validation_report(
        db_session, storage, start_date, end_date, activity_ids=activity_ids or None
    )
    combined_result["validation"] = validation
    combined_result["synced_activity_ids"] = activity_ids or []
    sync_jobs[job_id].update({
        "status": "completed",
        "result": combined_result,
        "end_time": datetime.now(timezone.utc),
        "message": validation.get("summary_text", "Synkronisering fullført"),
        "progress": {
            "phase": combined_result.get("_total_phases", 1),
            "total_phases": combined_result.get("_total_phases", 1),
            "percent": 100,
            "label": "Fullført",
        },
    })


@router.get("/status/{job_id}")
async def get_sync_status(job_id: str):
    """Henter status for en spesifikk bakgrunnsjobb."""
    job = _store_get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job_id,
        "job_type": job.get("job_type"),
        "status": job.get("status"),
        "is_active": job.get("status") in ACTIVE_JOB_STATUSES,
        "message": job.get("message"),
        "progress": job.get("progress"),
        "created_at": _dt_to_iso(job.get("created_at")),
        "start_time": _dt_to_iso(job.get("start_time")),
        "end_time": _dt_to_iso(job.get("end_time")),
        "result": job.get("result"),
        "error": job.get("error"),
    }

@router.post("/sync/database", status_code=200)
def trigger_db_sync(
    storage: DataStorage = Depends(get_data_storage),
    db: Session = Depends(get_db)
):
    """
    Synkroniserer data fra lokale JSON-filer til databasen.
    """
    # GarminClient er ikke nødvendig her, så vi kan sette den til None
    sync_service = SyncService(garmin_client=None, storage=storage, db_session=db)
    result = sync_service.sync_json_to_db()
    return result

@router.post("/activities", status_code=202)
async def trigger_activity_sync(
    request: SyncRequest,
    background_tasks: BackgroundTasks,
    storage: DataStorage = Depends(get_data_storage),
    garmin_client: GarminClient = Depends(get_garmin_client)
):
    """Starter synkronisering av aktiviteter for en gitt periode med automatisk FIT-data nedlasting og force refresh for nylige aktiviteter."""
    start_datetime = datetime.combine(request.start_date, datetime.min.time(), tzinfo=timezone.utc)
    end_datetime = datetime.combine(request.end_date, datetime.max.time(), tzinfo=timezone.utc)
    
    active = _find_active_activity_queue_job()
    if active:
        existing_job_id, existing_job = active
        return _existing_job_response(
            "Aktivitetssynk er allerede i gang. Returnerer eksisterende jobb.",
            existing_job_id,
            existing_job,
        )
    job_id = _create_job("activities_sync", "Aktivitetssynk er køet.")
    # Bruk force_refresh_recent=True for å sikre at nylige aktiviteter oppdateres
    background_tasks.add_task(
        run_activity_sync_with_fit_data,
        job_id,
        garmin_client,
        storage,
        start_datetime,
        end_datetime,
        True,  # force_refresh_recent
        100,   # fit_data_limit
        request.ignore_sync_state,
        request.fit_download_mode or "chunked",
    )
    
    return _completed_job_response(
        "Synkronisering av aktiviteter startet (inkluderer automatisk FIT-data nedlasting og force refresh for nylige aktiviteter).",
        job_id,
    )

@router.post("/activities/historical", status_code=202)
async def trigger_activity_sync_historical(
    start_date: date = Query(..., description="Startdato (YYYY-MM-DD)"),
    end_date: date = Query(..., description="Sluttdato (YYYY-MM-DD)"),
    background_tasks: BackgroundTasks = None,
    storage: DataStorage = Depends(get_data_storage),
    garmin_client: GarminClient = Depends(get_garmin_client)
):
    """Starter synkronisering for en gitt periode med ignore_sync_state=true og chunket FIT.
    Dette gjør det enkelt å trigge fra frontend uten JSON-body."""
    start_datetime = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    end_datetime = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)

    active = _find_active_activity_queue_job()
    if active:
        existing_job_id, existing_job = active
        return _existing_job_response(
            "Historisk aktivitetssynk er allerede i gang. Returnerer eksisterende jobb.",
            existing_job_id,
            existing_job,
        )
    job_id = _create_job("activities_sync", "Historisk aktivitetssynk er køet.")

    background_tasks.add_task(
        run_activity_sync_with_fit_data,
        job_id,
        garmin_client,
        storage,
        start_datetime,
        end_datetime,
        True,      # force_refresh_recent
        150,       # fit_data_limit
        True,      # ignore_sync_state
        "chunked"  # fit_download_mode
    )

    return _completed_job_response("Historisk synkronisering startet (ignore_sync_state, chunked FIT)", job_id)


@router.post("/fit-data/download/missing", status_code=202)
async def trigger_missing_fit_download(
    background_tasks: BackgroundTasks,
    storage: DataStorage = Depends(get_data_storage),
    garmin_client: GarminClient = Depends(get_garmin_client),
    limit: int = Query(50, ge=1, le=500, description="Maks antall manglende aktiviteter per kjøring")
):
    """Fortsetter nedlasting av manglende FIT-data i batcher."""
    active = _find_active_job_by_type("fit_download")
    if active:
        existing_job_id, existing_job = active
        return _existing_job_response(
            "FIT-nedlasting er allerede i gang. Returnerer eksisterende jobb.",
            existing_job_id,
            existing_job,
        )
    job_id = _create_job("fit_download", "FIT-nedlasting (manglende) er køet.")

    async def _run_missing_fit_job():
        db_session = None
        try:
            _mark_job_processing(job_id, "Laster ned manglende FIT-data...")
            db_session = SessionLocal()
            sync_service = SyncService(garmin_client, storage, db_session)
            result = await sync_service.download_fit_data_for_activities(limit=limit)
            sync_jobs[job_id].update({"status": "completed", "result": result, "end_time": datetime.now(timezone.utc)})
        except Exception as e:
            logger.critical(f"Feil i missing FIT-jobb {job_id}: {e}", exc_info=True)
            sync_jobs[job_id].update({"status": "failed", "error": str(e), "end_time": datetime.now(timezone.utc)})
        finally:
            if db_session:
                db_session.close()

    background_tasks.add_task(_run_missing_fit_job)
    res = _completed_job_response("Nedlasting av manglende FIT-data startet", job_id)
    res["limit"] = limit
    return res

@router.post("/activities/recent", status_code=202)
async def trigger_recent_activity_sync(
    background_tasks: BackgroundTasks,
    storage: DataStorage = Depends(get_data_storage),
    garmin_client: GarminClient = Depends(get_garmin_client)
):
    """Starter synkronisering av aktiviteter for de siste 30 dagene med force refresh og automatisk FIT-data nedlasting."""
    end_datetime = datetime.now(timezone.utc)
    start_datetime = end_datetime - timedelta(days=30)
    
    active = _find_active_activity_queue_job()
    if active:
        existing_job_id, existing_job = active
        return _existing_job_response(
            "Aktivitetssynk er allerede i gang. Returnerer eksisterende jobb.",
            existing_job_id,
            existing_job,
        )
    job_id = _create_job("activities_sync", "Synk av nye aktiviteter er køet.")
    background_tasks.add_task(
        run_activity_sync_with_fit_data,
        job_id,
        garmin_client,
        storage,
        start_datetime,
        end_datetime,
        True,   # force_refresh_recent
        150,    # fit_data_limit
        False,  # ignore_sync_state
        "chunked",  # fit_download_mode
    )
    
    return _completed_job_response(
        "Synkronisering av siste 30 dagers aktiviteter startet (med force refresh og automatisk FIT-data nedlasting).",
        job_id,
    )

@router.post("/health", status_code=202)
async def trigger_health_sync(
    request: SyncRequest,
    background_tasks: BackgroundTasks,
    storage: DataStorage = Depends(get_data_storage),
    garmin_client: GarminClient = Depends(get_garmin_client)
):
    """Starter synkronisering av helsedata for en gitt periode."""
    start_datetime = datetime.combine(request.start_date, datetime.min.time(), tzinfo=timezone.utc)
    end_datetime = datetime.combine(request.end_date, datetime.max.time(), tzinfo=timezone.utc)

    active = _find_active_job_by_type("health_sync")
    if active:
        existing_job_id, existing_job = active
        return _existing_job_response(
            "Helsesynk er allerede i gang. Returnerer eksisterende jobb.",
            existing_job_id,
            existing_job,
        )
    job_id = _create_job("health_sync", "Helsesynk er køet.")
    background_tasks.add_task(run_health_sync, job_id, garmin_client, storage, start_datetime, end_datetime)
    
    return _completed_job_response("Synkronisering av helsedata startet.", job_id)

@router.post("/health/recent", status_code=202)
async def trigger_recent_health_sync(
    background_tasks: BackgroundTasks,
    storage: DataStorage = Depends(get_data_storage),
    garmin_client: GarminClient = Depends(get_garmin_client)
):
    """Starter synkronisering av helsedata for de siste 90 dagene med force refresh for siste 30 dager."""
    end_datetime = datetime.now(timezone.utc)
    start_datetime = end_datetime - timedelta(days=90)
    
    active = _find_active_job_by_type("health_sync")
    if active:
        existing_job_id, existing_job = active
        return _existing_job_response(
            "Helsesynk er allerede i gang. Returnerer eksisterende jobb.",
            existing_job_id,
            existing_job,
        )
    job_id = _create_job("health_sync", "Helsesynk (recent) er køet.")
    background_tasks.add_task(run_health_sync_with_force, job_id, garmin_client, storage, start_datetime, end_datetime, True)
    
    return _completed_job_response(
        "Synkronisering av siste 90 dagers helsedata startet (med force refresh for siste 2 dager).",
        job_id,
    )

@router.post("/garmin-performance", status_code=202)
async def trigger_garmin_performance_metrics_sync(
    request: SyncRequest,
    background_tasks: BackgroundTasks,
    storage: DataStorage = Depends(get_data_storage),
    garmin_client: GarminClient = Depends(get_garmin_client)
):
    """Starter synkronisering av Garmin VO2max/status/load/endurance/hill-metrikker."""
    start_datetime = datetime.combine(request.start_date, datetime.min.time(), tzinfo=timezone.utc)
    end_datetime = datetime.combine(request.end_date, datetime.max.time(), tzinfo=timezone.utc)

    active = _find_active_job_by_type("garmin_performance_metrics_sync")
    if active:
        existing_job_id, existing_job = active
        return _existing_job_response(
            "Garmin performance metrics-synk er allerede i gang. Returnerer eksisterende jobb.",
            existing_job_id,
            existing_job,
        )
    job_id = _create_job("garmin_performance_metrics_sync", "Garmin performance metrics-synk er køet.")
    background_tasks.add_task(
        run_garmin_performance_metrics_sync,
        job_id,
        garmin_client,
        storage,
        start_datetime,
        end_datetime,
        True,
        request.ignore_sync_state,
    )
    return _completed_job_response("Synkronisering av Garmin performance metrics startet.", job_id)

@router.post("/garmin-performance/recent", status_code=202)
async def trigger_recent_garmin_performance_metrics_sync(
    background_tasks: BackgroundTasks,
    storage: DataStorage = Depends(get_data_storage),
    garmin_client: GarminClient = Depends(get_garmin_client)
):
    """Starter synkronisering av Garmin performance metrics for de siste 90 dagene."""
    end_datetime = datetime.now(timezone.utc)
    start_datetime = end_datetime - timedelta(days=90)

    active = _find_active_job_by_type("garmin_performance_metrics_sync")
    if active:
        existing_job_id, existing_job = active
        return _existing_job_response(
            "Garmin performance metrics-synk er allerede i gang. Returnerer eksisterende jobb.",
            existing_job_id,
            existing_job,
        )
    job_id = _create_job("garmin_performance_metrics_sync", "Garmin performance metrics recent-synk er køet.")
    background_tasks.add_task(
        run_garmin_performance_metrics_sync,
        job_id,
        garmin_client,
        storage,
        start_datetime,
        end_datetime,
        True,
        False,
    )
    return _completed_job_response("Synkronisering av siste 90 dagers Garmin performance metrics startet.", job_id)

@router.post("/fit-data/download", status_code=202)
async def trigger_fit_data_download(
    background_tasks: BackgroundTasks,
    limit: int = 50,
    storage: DataStorage = Depends(get_data_storage),
    garmin_client: GarminClient = Depends(get_garmin_client)
):
    """Starter nedlasting av FIT-data for aktiviteter som mangler detaljerte data."""
    active = _find_active_job_by_type("fit_download")
    if active:
        existing_job_id, existing_job = active
        return _existing_job_response(
            "FIT-nedlasting er allerede i gang. Returnerer eksisterende jobb.",
            existing_job_id,
            existing_job,
        )
    job_id = _create_job("fit_download", "FIT-nedlasting er køet.")
    background_tasks.add_task(run_fit_data_download, job_id, garmin_client, storage, None, limit)
    
    return _completed_job_response(f"FIT-data nedlasting startet for opptil {limit} aktiviteter.", job_id)

@router.post("/fit-data/download/period", status_code=202)
async def trigger_fit_data_download_period_endpoint(
    request: SyncRequest,
    background_tasks: BackgroundTasks,
    storage: DataStorage = Depends(get_data_storage),
    garmin_client: GarminClient = Depends(get_garmin_client)
):
    """Starter nedlasting av FIT-data for en spesifikk periode."""
    start_datetime = datetime.combine(request.start_date, datetime.min.time(), tzinfo=timezone.utc)
    end_datetime = datetime.combine(request.end_date, datetime.max.time(), tzinfo=timezone.utc)

    active = _find_active_job_by_type("fit_download")
    if active:
        existing_job_id, existing_job = active
        return _existing_job_response(
            "FIT-nedlasting er allerede i gang. Returnerer eksisterende jobb.",
            existing_job_id,
            existing_job,
        )
    job_id = _create_job("fit_download", "FIT-periode-nedlasting er køet.")
    background_tasks.add_task(run_fit_data_download_period, job_id, garmin_client, storage, start_datetime, end_datetime)
    
    return _completed_job_response(
        f"FIT-data nedlasting for periode {request.start_date} til {request.end_date} startet.",
        job_id,
    )

@router.post("/training-effect/refresh", status_code=202)
async def trigger_training_effect_refresh(
    background_tasks: BackgroundTasks,
    force: bool = Query(False, description="Oppdater ALLE aktiviteter (også de med verdier)"),
    storage: DataStorage = Depends(get_data_storage),
    garmin_client: GarminClient = Depends(get_garmin_client),
):
    """Henter aerob/anaerob effekt fra Garmin for aktiviteter som mangler eller viser 0."""
    active = _find_active_job_by_type("training_effect_sync")
    if active:
        existing_job_id, existing_job = active
        return _existing_job_response(
            "Training Effect-synk er allerede i gang. Returnerer eksisterende jobb.",
            existing_job_id,
            existing_job,
        )
    job_id = _create_job("training_effect_sync", "Training Effect-synk er køet.")
    background_tasks.add_task(run_training_effect_refresh, job_id, garmin_client, storage, force)
    msg = "Henter Training Effect for aktiviteter som mangler eller har 0."
    if force:
        msg = "Henter Training Effect for ALLE aktiviteter (force)."
    return _completed_job_response(msg, job_id)

@router.post("/sync/historical/{start_year}")
async def sync_historical_data(
    start_year: int, 
    garmin_client: GarminClient = Depends(get_garmin_client),
    storage: DataStorage = Depends(get_data_storage)
):
    """Start synkronisering av historiske data (aktiviteter) fra et gitt år."""
    try:
        if start_year < 2010 or start_year > datetime.now().year:
            raise HTTPException(
                status_code=400,
                detail=f"Start-år må være mellom 2010 og {datetime.now().year}"
            )
        
        logger.info(f"Starter historisk datasynkroniseringsjobb for år {start_year} via API-endepunkt.")

        sync_result = await garmin_client.sync_historical_data(start_year)

        activities_to_save = sync_result.get("all_activities", [])


        if activities_to_save:
            logger.info(f"Lagrer {len(activities_to_save)} aktiviteter fra historisk synkronisering for {start_year}.")
            storage.save_activities(activities_to_save)
        else:
            logger.info(f"Ingen nye aktiviteter å lagre fra historisk synkronisering for {start_year}.")



        response_stats = {
            "year": sync_result.get("year"),
            "total_activities_synced": sync_result.get("total_activities_synced"),

        }

        logger.info(f"Historisk datasynkroniseringsjobb for år {start_year} fullført. Statistikk: {response_stats}")
        return {
            "message": f"Synkronisering for {start_year} fullført",
            "statistics": response_stats
        }

    except AttributeError as ae: 
        logger.error(f"Metoden sync_historical_data mangler sannsynligvis i GarminClient: {ae}", exc_info=True)
        raise HTTPException(status_code=501, detail="Funksjonalitet for historisk synkronisering er ikke korrekt implementert i klienten.")
    except GarthException as ge:
        logger.error(f"Garmin API feil under historisk synkronisering for {start_year}: {ge}", exc_info=True)
        if "429" in str(ge) or (hasattr(ge, 'response') and ge.response is not None and ge.response.status_code == 429):
            raise HTTPException(
                status_code=429,
                detail="For mange forespørsler til Garmin Connect under historisk synk. Vennligst vent og prøv igjen."
            )
        raise HTTPException(status_code=503, detail=f"Feil ved kommunikasjon med Garmin Connect under historisk synk: {str(ge)}")
    except Exception as e:
        logger.error(f"Uventet feil under historisk synkronisering for {start_year}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"En intern feil oppstod under historisk synkronisering: {str(e)}")

@router.post("/sync-json-to-db", status_code=status.HTTP_200_OK)
def sync_json_to_db_endpoint(db: Session = Depends(get_db)):
    """
    Et endepunkt for manuelt å trigge synkronisering fra JSON-filer til databasen.
    """
    # Denne funksjonen er nå mindre relevant, men beholdes for eventuell fremtidig bruk.
    sync_service = SyncService(None, get_data_storage(), db) # GarminClient er ikke nødvendig her
    result = sync_service.sync_json_to_db()
    return result

async def run_full_sync(job_id: str, garmin_client: GarminClient, storage: DataStorage, start_date: datetime, end_date: datetime, ignore_sync_state: bool = False):
    """Kjører full synkronisering av alle data i bakgrunnen.
    
    Aktiviteter og FIT-data synkroniseres fra start_date.
    Helsedata (HRV, Body Battery, Training Effect) begrenses til 2020 eller senere.
    """
    db_session = None
    try:
        _mark_job_processing(
            job_id,
            "Steg 1/4: Aktiviteter, FIT, helse og TE…",
            phase=0,
            total_phases=FULL_SYNC_PHASES,
        )

        db_session = SessionLocal()
        sync_service = SyncService(garmin_client, storage, db_session)
        
        # Begrens helsedata, HRV og Body Battery til 2020 eller senere
        # (Aktiviteter og FIT-data kan gå tilbake til 2008)
        health_data_cutoff = datetime(2020, 1, 1, tzinfo=timezone.utc)
        health_start_date = max(start_date, health_data_cutoff)
        
        if start_date < health_data_cutoff:
            logger.info(f"Full sync: Aktiviteter fra {start_date.date()}, helsedata fra {health_start_date.date()}")
        
        activity_result = await sync_service.sync_activities_with_fit_data(
            start_date, 
            end_date,
            force_refresh_recent=True,
            fit_data_limit=150,
            ignore_sync_state=ignore_sync_state,
            fit_download_mode="chunked"
        )

        set_job_phase(job_id, 1, FULL_SYNC_PHASES, "Steg 2/4: Garmin performance metrics…")
        performance_result = await sync_service.sync_garmin_performance_metrics(
            health_start_date,
            end_date,
            force_refresh_recent=True,
            ignore_sync_state=ignore_sync_state,
        )

        set_job_phase(job_id, 2, FULL_SYNC_PHASES, "Steg 3/4: HRV til database…")
        hrv_service = HRVService(storage)
        hrv_result = hrv_service.sync_hrv_data_to_database(
            db_session,
            health_start_date.strftime('%Y-%m-%d'),
            end_date.strftime('%Y-%m-%d'),
        )
        body_battery_result = {"message": "Allerede synket via helsedata i steg 1"}

        set_job_phase(job_id, 3, FULL_SYNC_PHASES, "Steg 4/4: Beregninger og caching…")
        await run_calculations_and_caching(job_id, db_session, start_date, end_date, storage)

        activity_ids = _activity_ids_from_sync_result(activity_result)
        combined_result = {
            "_total_phases": FULL_SYNC_PHASES,
            "activities": activity_result,
            "garmin_performance_metrics": performance_result,
            "hrv_sync": hrv_result,
            "body_battery_sync": body_battery_result,
            "message": "Full synkronisering fullført",
        }
        _finalize_sync_job(
            job_id, combined_result, db_session, storage, start_date, end_date, activity_ids
        )
        logger.info(f"Full synkronisering fullført for jobb {job_id}")
        
    except Exception as e:
        logger.critical(f"Feil i full synkronisering (jobb {job_id}): {e}", exc_info=True)
        sync_jobs[job_id].update({
            "status": "failed", 
            "error": str(e), 
            "end_time": datetime.now(timezone.utc)
        })
    finally:
        if db_session:
            db_session.close()

async def run_calculations_and_caching(job_id: str, db_session: Session, start_date: datetime, end_date: datetime, storage: DataStorage):
    """Kjører alle nødvendige beregninger og caching for raskere datahenting."""
    try:
        from ..services.power_service import PowerService
        from ..services.training_stress_service import TrainingStressService
        
        # 1. Beregn power for alle løpeaktiviteter i perioden
        sync_jobs[job_id]["message"] = "Beregner power for løpeaktiviteter..."
        power_service = PowerService(storage)
        
        # Hent løpeaktiviteter i perioden som mangler power
        from sqlalchemy import and_
        from ..database.models.activity import Activity
        from ..utils.activity_filters import apply_running_activity_filter
        
        running_activities = apply_running_activity_filter(
            db_session.query(Activity).filter(
                and_(
                    Activity.start_time >= start_date,
                    Activity.start_time <= end_date,
                    Activity.average_power.is_(None),
                )
            )
        ).all()
        
        power_calculated = 0
        for activity in running_activities:
            try:
                result = power_service.calculate_activity_power(int(activity.activity_id), db_session)
                if result:
                    power_calculated += 1
            except Exception as e:
                logger.warning(f"Kunne ikke beregne power for aktivitet {activity.activity_id}: {e}")
        
        # 2. Beregn Training Stress Score for perioden
        sync_jobs[job_id]["message"] = "Beregner Training Stress Score..."
        training_stress_service = TrainingStressService(db_session)
        
        from ..services.sync_modules.metrics_service import tss_needs_refresh

        activities_in_period = db_session.query(Activity).filter(
            and_(
                Activity.start_time >= start_date,
                Activity.start_time <= end_date,
            )
        ).all()

        tss_calculated = 0
        for activity in activities_in_period:
            if not tss_needs_refresh(activity):
                continue
            try:
                tss = training_stress_service.calculate_tss_for_activity(activity)
                if tss is not None and tss >= 0:
                    activity.training_stress_score = tss
                    tss_calculated += 1
            except Exception as e:
                logger.warning(f"Kunne ikke beregne TSS for aktivitet {activity.activity_id}: {e}")
        
        # 3. Lagre endringer til database
        if power_calculated > 0 or tss_calculated > 0:
            db_session.commit()
            logger.info(f"Beregninger fullført: {power_calculated} power-beregninger, {tss_calculated} TSS-beregninger")
        
        # 4. Oppdater cache for raskere datahenting
        sync_jobs[job_id]["message"] = "Oppdaterer cache..."
        # Her kan vi legge til mer caching-logikk hvis nødvendig
        
        return {
            "power_calculated": power_calculated,
            "tss_calculated": tss_calculated
        }
        
    except Exception as e:
        logger.error(f"Feil under beregninger og caching: {e}")
        raise

@router.post("/full-sync", status_code=202)
async def trigger_full_sync(
    request: SyncRequest,
    background_tasks: BackgroundTasks,
    storage: DataStorage = Depends(get_data_storage),
    garmin_client: GarminClient = Depends(get_garmin_client)
):
    """
    Starter full synkronisering av alle data for en gitt periode.
    - Aktiviteter og FIT-data: Fra start_date til end_date
    - Helsedata (HRV, Body Battery, Training Effect): Kun fra 2020-01-01 eller senere
    """
    start_datetime = datetime.combine(request.start_date, datetime.min.time(), tzinfo=timezone.utc)
    end_datetime = datetime.combine(request.end_date, datetime.max.time(), tzinfo=timezone.utc)
    
    active = _find_active_job_by_type("full_sync")
    if active:
        existing_job_id, existing_job = active
        return _existing_job_response(
            "Full synkronisering er allerede i gang. Returnerer eksisterende jobb.",
            existing_job_id,
            existing_job,
        )
    job_id = _create_job("full_sync", "Full synkronisering er køet.")
    background_tasks.add_task(
        run_full_sync, 
        job_id, 
        garmin_client, 
        storage, 
        start_datetime, 
        end_datetime,
        request.ignore_sync_state  # Send ignore_sync_state videre!
    )
    
    return _completed_job_response(
        f"Full synkronisering startet for perioden {request.start_date} til {request.end_date}. Dette inkluderer aktiviteter, FIT-data, helsedata og Training Effect data.",
        job_id,
    )

async def run_calculations_only(job_id: str, storage: DataStorage, start_date: datetime, end_date: datetime):
    """Kjører kun beregninger og caching for eksisterende data."""
    db_session = None
    try:
        _mark_job_processing(job_id, "Starter beregninger og caching...")
        db_session = SessionLocal()
        
        result = await run_calculations_and_caching(job_id, db_session, start_date, end_date, storage)
        
        sync_jobs[job_id].update({
            "status": "completed", 
            "result": result, 
            "end_time": datetime.now(timezone.utc)
        })
        
    except Exception as e:
        logger.critical(f"Feil i beregninger (jobb {job_id}): {e}", exc_info=True)
        sync_jobs[job_id].update({
            "status": "failed", 
            "error": str(e), 
            "end_time": datetime.now(timezone.utc)
        })
    finally:
        if db_session:
            db_session.close()

async def run_new_activities_sync(job_id: str, garmin_client: GarminClient, storage: DataStorage):
    """
    Kjører synkronisering av nye aktiviteter i bakgrunnen.

    Viktig:
    - Når vi synkroniserer nye aktiviteter, skal vi alltid hente ALLE treningsaktiviteter
      fra og med datoen til siste lagrede aktivitet og frem til i dag.
    - Vi baserer oss kun på faktisk lagrede aktiviteter i databasen, ikke på SyncState
      for aktiviteter eller helsedata, slik at vi ikke risikerer å hoppe over økter
      hvis SyncState er kommet lenger enn dataene i databasen.
    """
    db_session = None
    try:
        _mark_job_processing(job_id, "Forbereder synk…", phase=0, total_phases=NEW_ACTIVITIES_PHASES)

        db_session = SessionLocal()
        
        # Finn siste aktivitet i databasen
        latest_activity = db_session.query(Activity).order_by(Activity.start_time.desc()).first()
        
        if latest_activity:
            # Bruk DATOEN til siste aktivitet som startdato (fra og med denne dagen)
            # Dette sikrer at vi får med alle økter den dagen, også hvis noen mangler
            # eller har tidligere tidspunkt enn siste lagrede aktivitet.
            last_activity_time = latest_activity.start_time
            if last_activity_time.tzinfo is None:
                last_activity_time = last_activity_time.replace(tzinfo=timezone.utc)

            start_date = datetime.combine(
                last_activity_time.date(),
                datetime.min.time(),
                tzinfo=timezone.utc,
            )
            
            sync_jobs[job_id]["message"] = f"Synkroniserer fra {start_date.strftime('%Y-%m-%d %H:%M')} til nå..."
            logger.info(f"Starter synkronisering av nye aktiviteter fra {start_date} til nå")
        else:
            # Hvis ingen aktiviteter finnes, synkroniser siste 30 dager
            start_date = datetime.now(timezone.utc) - timedelta(days=30)
            sync_jobs[job_id]["message"] = f"Ingen eksisterende aktiviteter, synkroniserer siste 30 dager..."
            logger.info(f"Ingen eksisterende aktiviteter, starter synkronisering av siste 30 dager")
        
        end_date = datetime.now(timezone.utc)
        
        sync_service = SyncService(garmin_client, storage, db_session)
        
        set_job_phase(
            job_id,
            0,
            NEW_ACTIVITIES_PHASES,
            f"Steg 1/{NEW_ACTIVITIES_PHASES}: Aktiviteter, FIT, helse og TE…",
        )
        activity_result = await sync_service.sync_activities_with_fit_data(
            start_date,
            end_date,
            force_refresh_recent=True,
            fit_data_limit=150,
            ignore_sync_state=True,
            fit_download_mode="chunked",
        )

        set_job_phase(job_id, 1, NEW_ACTIVITIES_PHASES, f"Steg 2/{NEW_ACTIVITIES_PHASES}: Garmin performance metrics…")
        performance_result = await sync_service.sync_garmin_performance_metrics(
            start_date,
            end_date,
            force_refresh_recent=True,
            ignore_sync_state=True,
        )

        set_job_phase(job_id, 2, NEW_ACTIVITIES_PHASES, f"Steg 3/{NEW_ACTIVITIES_PHASES}: HRV til database…")
        hrv_service = HRVService(storage)
        hrv_result = hrv_service.sync_hrv_data_to_database(
            db_session,
            start_date.strftime('%Y-%m-%d'),
            end_date.strftime('%Y-%m-%d'),
        )
        body_battery_result = {"message": "Allerede synket via helsedata i steg 1"}

        set_job_phase(job_id, 3, NEW_ACTIVITIES_PHASES, f"Steg 4/{NEW_ACTIVITIES_PHASES}: Beregninger og caching…")
        await run_calculations_and_caching(job_id, db_session, start_date, end_date, storage)

        activity_ids = _activity_ids_from_sync_result(activity_result)
        combined_result = {
            "_total_phases": NEW_ACTIVITIES_PHASES,
            "activities": activity_result,
            "garmin_performance_metrics": performance_result,
            "hrv_sync": hrv_result,
            "body_battery_sync": body_battery_result,
            "period": {
                "start": start_date.strftime('%Y-%m-%d %H:%M'),
                "end": end_date.strftime('%Y-%m-%d %H:%M'),
            },
            "message": "Synkronisering av nye aktiviteter fullført",
        }
        _finalize_sync_job(
            job_id, combined_result, db_session, storage, start_date, end_date, activity_ids
        )
        logger.info(f"Synkronisering av nye aktiviteter fullført for jobb {job_id}")
        
    except Exception as e:
        logger.critical(f"Feil i synkronisering av nye aktiviteter (jobb {job_id}): {e}", exc_info=True)
        sync_jobs[job_id].update({
            "status": "failed", 
            "error": str(e), 
            "end_time": datetime.now(timezone.utc)
        })
    finally:
        if db_session:
            db_session.close()

@router.post("/calculations", status_code=202)
async def trigger_calculations(
    request: SyncRequest,
    background_tasks: BackgroundTasks,
    storage: DataStorage = Depends(get_data_storage)
):
    """
    Starter beregninger og caching for eksisterende data for en gitt periode.
    Dette inkluderer power-beregninger og Training Stress Score.
    """
    start_datetime = datetime.combine(request.start_date, datetime.min.time(), tzinfo=timezone.utc)
    end_datetime = datetime.combine(request.end_date, datetime.max.time(), tzinfo=timezone.utc)
    
    active = _find_active_job_by_type("calculations")
    if active:
        existing_job_id, existing_job = active
        return _existing_job_response(
            "Beregninger/caching er allerede i gang. Returnerer eksisterende jobb.",
            existing_job_id,
            existing_job,
        )
    job_id = _create_job("calculations", "Beregninger/caching er køet.")
    background_tasks.add_task(run_calculations_only, job_id, storage, start_datetime, end_datetime)
    
    return _completed_job_response(
        f"Beregninger og caching startet for perioden {request.start_date} til {request.end_date}.",
        job_id,
    )

@router.post("/new-activities", status_code=202)
async def trigger_new_activities_sync(
    background_tasks: BackgroundTasks,
    storage: DataStorage = Depends(get_data_storage),
    garmin_client: GarminClient = Depends(get_garmin_client)
):
    """
    Starter synkronisering av nye aktiviteter fra siste lagrede aktivitet.
    Dette inkluderer aktiviteter, FIT-data, helsedata, Training Effect data og beregninger.
    """
    active = _find_active_activity_queue_job()
    if active:
        existing_job_id, existing_job = active
        return _existing_job_response(
            "Aktivitetssynk er allerede i gang. Returnerer eksisterende jobb.",
            existing_job_id,
            existing_job,
        )
    job_id = _create_job("new_activities_sync", "Synk av nye aktiviteter er køet.")
    background_tasks.add_task(run_new_activities_sync, job_id, garmin_client, storage)
    
    return _completed_job_response(
        "Synkronisering av nye aktiviteter startet. Dette vil synkronisere fra siste lagrede aktivitet til nå.",
        job_id,
    )

def run_hrv_sync(start_date: Optional[str] = None, end_date: Optional[str] = None, db_session: Session = None) -> Dict[str, Any]:
    """Synkroniserer HRV-data fra parquet-filer til databasen."""
    try:
        storage = DataStorage(settings.DATA_DIR)
        hrv_service = HRVService(storage)
        
        result = hrv_service.sync_hrv_data_to_database(db_session, start_date, end_date)
        
        if result["success"]:
            return {
                "status": "completed",
                "message": result["message"],
                "synced_records": result["synced_records"],
                "skipped_records": result["skipped_records"],
                "total_records": result.get("total_records", 0)
            }
        else:
            return {
                "status": "failed",
                "message": result["message"]
            }
            
    except Exception as e:
        logger.error(f"Feil ved HRV-synkronisering: {e}")
        return {
            "status": "failed",
            "message": f"Feil ved HRV-synkronisering: {str(e)}"
        }

@router.post("/hrv-sync")
async def sync_hrv_data(
    start_date: Optional[str] = Query(None, description="Startdato for HRV-synkronisering (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Sluttdato for HRV-synkronisering (YYYY-MM-DD)"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db)
):
    """Synkroniserer HRV-data fra parquet-filer til databasen for raskere tilgang."""
    try:
        active = _find_active_job_by_type("hrv_sync")
        if active:
            existing_job_id, existing_job = active
            return _existing_job_response(
                "HRV-synk er allerede i gang. Returnerer eksisterende jobb.",
                existing_job_id,
                existing_job,
            )
        job_id = _create_job("hrv_sync", "HRV-synk er køet.")
        
        # Start synkronisering som bakgrunnsjobb
        background_tasks.add_task(
            run_hrv_sync_task,
            job_id=job_id,
            start_date=start_date,
            end_date=end_date
        )
        
        _mark_job_processing(job_id, "Starter HRV-synkronisering...")
        
        logger.info(f"HRV-synkronisering startet med jobb-ID: {job_id}")
        
        job = sync_jobs[job_id]
        return {
            "job_id": job_id,
            "message": "HRV-synkronisering startet",
            "status": job["status"],
            "job_type": job.get("job_type"),
            "reused_existing_job": False,
        }
        
    except Exception as e:
        logger.error(f"Feil ved start av HRV-synkronisering: {e}")
        raise HTTPException(status_code=500, detail=f"Feil ved start av HRV-synkronisering: {str(e)}")

def run_hrv_sync_task(job_id: str, start_date: Optional[str] = None, end_date: Optional[str] = None):
    """Bakgrunnsjobb for HRV-synkronisering."""
    try:
        # Opprett ny database session for bakgrunnsjobb
        db = SessionLocal()
        try:
            result = run_hrv_sync(start_date, end_date, db)
            
            # Oppdater jobb-status
            sync_jobs[job_id].update({
                "status": result["status"],
                "message": result["message"],
                "result": result,
                "end_time": datetime.now(timezone.utc)
            })
            
            logger.info(f"HRV-synkronisering fullført for jobb {job_id}: {result['message']}")
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Feil i HRV-synkroniseringsjobb {job_id}: {e}")
        sync_jobs[job_id].update({
            "status": "failed",
            "message": f"Feil ved HRV-synkronisering: {str(e)}",
            "error": str(e),
            "end_time": datetime.now(timezone.utc)
        })

async def run_body_battery_sync(start_date: Optional[str] = None, end_date: Optional[str] = None, db_session: Session = None) -> Dict[str, Any]:
    """Synkroniserer Body Battery-data fra Garmin til databasen."""
    try:
        garmin_client = GarminClient(
            email=settings.GARMIN_EMAIL,
            password=settings.GARMIN_PASSWORD,
            token_dir=settings.TOKEN_DIR
        )
        body_battery_service = BodyBatteryService(garmin_client)
        
        # Bruk standard tidsperiode hvis ikke spesifisert
        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        if not end_date:
            end_date = datetime.now().strftime('%Y-%m-%d')
        
        result = await body_battery_service.sync_body_battery_data_to_database(db_session, start_date, end_date)
        
        return {
            "status": "completed",
            "message": result["message"],
            "synced_records": result["synced_records"],
            "updated_records": result.get("updated_records", 0),
            "total_processed": result.get("total_processed", 0)
        }
            
    except Exception as e:
        logger.error(f"Feil ved Body Battery-synkronisering: {e}")
        return {
            "status": "failed",
            "message": f"Feil ved Body Battery-synkronisering: {str(e)}"
        }

@router.post("/body-battery-sync")
async def sync_body_battery_data(
    start_date: Optional[str] = Query(None, description="Startdato for Body Battery-synkronisering (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Sluttdato for Body Battery-synkronisering (YYYY-MM-DD)"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db)
):
    """Synkroniserer Body Battery-data fra Garmin til databasen."""
    try:
        active = _find_active_job_by_type("body_battery_sync")
        if active:
            existing_job_id, existing_job = active
            return _existing_job_response(
                "Body Battery-synk er allerede i gang. Returnerer eksisterende jobb.",
                existing_job_id,
                existing_job,
            )
        job_id = _create_job("body_battery_sync", "Body Battery-synk er køet.")
        
        # Start synkronisering som bakgrunnsjobb
        background_tasks.add_task(
            run_body_battery_sync_task,
            job_id=job_id,
            start_date=start_date,
            end_date=end_date
        )
        
        _mark_job_processing(job_id, "Starter Body Battery-synkronisering...")
        
        logger.info(f"Body Battery-synkronisering startet med jobb-ID: {job_id}")
        
        job = sync_jobs[job_id]
        return {
            "job_id": job_id,
            "message": "Body Battery-synkronisering startet",
            "status": job["status"],
            "job_type": job.get("job_type"),
            "reused_existing_job": False,
        }
        
    except Exception as e:
        logger.error(f"Feil ved start av Body Battery-synkronisering: {e}")
        raise HTTPException(status_code=500, detail=f"Feil ved start av Body Battery-synkronisering: {str(e)}")

def run_body_battery_sync_task(job_id: str, start_date: Optional[str] = None, end_date: Optional[str] = None):
    """Bakgrunnsjobb for Body Battery-synkronisering."""
    try:
        # Opprett ny database session for bakgrunnsjobb
        db = SessionLocal()
        try:
            # Kjør async funksjon i en event loop
            import asyncio
            result = asyncio.run(run_body_battery_sync(start_date, end_date, db))
            
            # Oppdater jobb-status
            sync_jobs[job_id].update({
                "status": result["status"],
                "message": result["message"],
                "result": result,
                "end_time": datetime.now(timezone.utc)
            })
            
            logger.info(f"Body Battery-synkronisering fullført for jobb {job_id}: {result['message']}")
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Feil i Body Battery-synkroniseringsjobb {job_id}: {e}")
        sync_jobs[job_id].update({
            "status": "failed",
            "message": f"Feil ved Body Battery-synkronisering: {str(e)}",
            "error": str(e),
            "end_time": datetime.now(timezone.utc)
        })
