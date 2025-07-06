from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from datetime import date, datetime, timezone, timedelta
import logging
from sqlalchemy.orm import Session
import pytz
import asyncio
from fastapi import status
import uuid
from typing import Dict

from ..services.garmin_client import GarminClient
from ..storage import DataStorage
from ..services.sync_service import SyncService
from ..dependencies import get_garmin_client, get_data_storage, get_db
from ..database.session import SessionLocal
from garth.exc import GarthException
from ..config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

sync_jobs: Dict[str, Dict] = {}

class SyncRequest(BaseModel):
    start_date: date
    end_date: date

async def run_activity_sync(job_id: str, garmin_client: GarminClient, storage: DataStorage, start_date: datetime, end_date: datetime):
    """Kjører aktivitetssynkronisering i bakgrunnen."""
    db_session = None
    try:
        sync_jobs[job_id]["status"] = "processing"
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
        sync_jobs[job_id]["status"] = "processing"
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
        sync_jobs[job_id]["status"] = "processing"
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
        sync_jobs[job_id]["status"] = "processing"
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

@router.get("/status/{job_id}")
async def get_sync_status(job_id: str):
    """Henter status for en spesifikk bakgrunnsjobb."""
    job = sync_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

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
    """Starter synkronisering av aktiviteter for en gitt periode."""
    start_datetime = datetime.combine(request.start_date, datetime.min.time(), tzinfo=timezone.utc)
    end_datetime = datetime.combine(request.end_date, datetime.max.time(), tzinfo=timezone.utc)
    
    job_id = str(uuid.uuid4())
    sync_jobs[job_id] = {"status": "queued", "start_time": datetime.now(timezone.utc)}
    background_tasks.add_task(run_activity_sync, job_id, garmin_client, storage, start_datetime, end_datetime)
    
    return {"message": "Synkronisering av aktiviteter startet.", "job_id": job_id}

@router.post("/activities/recent", status_code=202)
async def trigger_recent_activity_sync(
    background_tasks: BackgroundTasks,
    storage: DataStorage = Depends(get_data_storage),
    garmin_client: GarminClient = Depends(get_garmin_client)
):
    """Starter synkronisering av aktiviteter for de siste 30 dagene med force refresh."""
    end_datetime = datetime.now(timezone.utc)
    start_datetime = end_datetime - timedelta(days=30)
    
    job_id = str(uuid.uuid4())
    sync_jobs[job_id] = {"status": "queued", "start_time": datetime.now(timezone.utc)}
    background_tasks.add_task(run_activity_sync_with_force, job_id, garmin_client, storage, start_datetime, end_datetime, True)
    
    return {"message": "Synkronisering av siste 30 dagers aktiviteter startet (med force refresh).", "job_id": job_id}

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

    job_id = str(uuid.uuid4())
    sync_jobs[job_id] = {"status": "queued", "start_time": datetime.now(timezone.utc)}
    background_tasks.add_task(run_health_sync, job_id, garmin_client, storage, start_datetime, end_datetime)
    
    return {"message": "Synkronisering av helsedata startet.", "job_id": job_id}

@router.post("/health/recent", status_code=202)
async def trigger_recent_health_sync(
    background_tasks: BackgroundTasks,
    storage: DataStorage = Depends(get_data_storage),
    garmin_client: GarminClient = Depends(get_garmin_client)
):
    """Starter synkronisering av helsedata for de siste 90 dagene med force refresh for siste 30 dager."""
    end_datetime = datetime.now(timezone.utc)
    start_datetime = end_datetime - timedelta(days=90)
    
    job_id = str(uuid.uuid4())
    sync_jobs[job_id] = {"status": "queued", "start_time": datetime.now(timezone.utc)}
    background_tasks.add_task(run_health_sync_with_force, job_id, garmin_client, storage, start_datetime, end_datetime, True)
    
    return {"message": "Synkronisering av siste 90 dagers helsedata startet (med force refresh for siste 2 dager).", "job_id": job_id}

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
