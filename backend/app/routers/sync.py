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

async def run_activity_sync_with_fit_data(job_id: str, garmin_client: GarminClient, storage: DataStorage, start_date: datetime, end_date: datetime, force_refresh_recent: bool = False, fit_data_limit: int = 100):
    """Kjører aktivitetssynkronisering i bakgrunnen med automatisk FIT-data nedlasting."""
    db_session = None
    try:
        sync_jobs[job_id]["status"] = "processing"
        db_session = SessionLocal()
        sync_service = SyncService(garmin_client, storage, db_session)
        result = await sync_service.sync_activities_with_fit_data(start_date, end_date, force_refresh_recent, fit_data_limit)
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

async def run_fit_data_download(job_id: str, garmin_client: GarminClient, storage: DataStorage, activity_ids: list = None, limit: int = None):
    """Kjører FIT-data nedlasting i bakgrunnen."""
    db_session = None
    try:
        sync_jobs[job_id]["status"] = "processing"
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

async def run_fit_data_download_period(job_id: str, garmin_client: GarminClient, storage: DataStorage, start_date: datetime, end_date: datetime):
    """Kjører FIT-data nedlasting for en periode i bakgrunnen."""
    db_session = None
    try:
        sync_jobs[job_id]["status"] = "processing"
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
    """Starter synkronisering av aktiviteter for en gitt periode med automatisk FIT-data nedlasting og force refresh for nylige aktiviteter."""
    start_datetime = datetime.combine(request.start_date, datetime.min.time(), tzinfo=timezone.utc)
    end_datetime = datetime.combine(request.end_date, datetime.max.time(), tzinfo=timezone.utc)
    
    job_id = str(uuid.uuid4())
    sync_jobs[job_id] = {"status": "queued", "start_time": datetime.now(timezone.utc)}
    # Bruk force_refresh_recent=True for å sikre at nylige aktiviteter oppdateres
    background_tasks.add_task(run_activity_sync_with_fit_data, job_id, garmin_client, storage, start_datetime, end_datetime, True, 100)
    
    return {"message": "Synkronisering av aktiviteter startet (inkluderer automatisk FIT-data nedlasting og force refresh for nylige aktiviteter).", "job_id": job_id}

@router.post("/activities/recent", status_code=202)
async def trigger_recent_activity_sync(
    background_tasks: BackgroundTasks,
    storage: DataStorage = Depends(get_data_storage),
    garmin_client: GarminClient = Depends(get_garmin_client)
):
    """Starter synkronisering av aktiviteter for de siste 30 dagene med force refresh og automatisk FIT-data nedlasting."""
    end_datetime = datetime.now(timezone.utc)
    start_datetime = end_datetime - timedelta(days=30)
    
    job_id = str(uuid.uuid4())
    sync_jobs[job_id] = {"status": "queued", "start_time": datetime.now(timezone.utc)}
    background_tasks.add_task(run_activity_sync_with_fit_data, job_id, garmin_client, storage, start_datetime, end_datetime, True, 150)
    
    return {"message": "Synkronisering av siste 30 dagers aktiviteter startet (med force refresh og automatisk FIT-data nedlasting).", "job_id": job_id}

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

@router.post("/fit-data/download", status_code=202)
async def trigger_fit_data_download(
    background_tasks: BackgroundTasks,
    limit: int = 50,
    storage: DataStorage = Depends(get_data_storage),
    garmin_client: GarminClient = Depends(get_garmin_client)
):
    """Starter nedlasting av FIT-data for aktiviteter som mangler detaljerte data."""
    job_id = str(uuid.uuid4())
    sync_jobs[job_id] = {"status": "queued", "start_time": datetime.now(timezone.utc)}
    background_tasks.add_task(run_fit_data_download, job_id, garmin_client, storage, None, limit)
    
    return {"message": f"FIT-data nedlasting startet for opptil {limit} aktiviteter.", "job_id": job_id}

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

    job_id = str(uuid.uuid4())
    sync_jobs[job_id] = {"status": "queued", "start_time": datetime.now(timezone.utc)}
    background_tasks.add_task(run_fit_data_download_period, job_id, garmin_client, storage, start_datetime, end_datetime)
    
    return {"message": f"FIT-data nedlasting for periode {request.start_date} til {request.end_date} startet.", "job_id": job_id}

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

async def run_full_sync(job_id: str, garmin_client: GarminClient, storage: DataStorage, start_date: datetime, end_date: datetime):
    """Kjører full synkronisering av alle data i bakgrunnen."""
    db_session = None
    try:
        sync_jobs[job_id]["status"] = "processing"
        sync_jobs[job_id]["message"] = "Starter full synkronisering..."
        db_session = SessionLocal()
        sync_service = SyncService(garmin_client, storage, db_session)
        
        # 1. Synkroniser aktiviteter med FIT-data
        sync_jobs[job_id]["message"] = "Synkroniserer aktiviteter..."
        activity_result = await sync_service.sync_activities_with_fit_data(start_date, end_date, True, 100)
        
        # 2. Synkroniser helsedata
        sync_jobs[job_id]["message"] = "Synkroniserer helsedata..."
        await sync_service.sync_health_data(start_date, end_date, True)
        
        # 3. Synkroniser Training Effect data
        sync_jobs[job_id]["message"] = "Synkroniserer Training Effect data..."
        te_result = await sync_service.sync_training_effect_data(start_date, end_date, True)
        
        # 4. Kjør alle beregninger og caching
        sync_jobs[job_id]["message"] = "Kjører beregninger og caching..."
        await run_calculations_and_caching(job_id, db_session, start_date, end_date)
        
        # Kombiner resultater
        combined_result = {
            "activities": activity_result,
            "health_data": "OK",
            "training_effect": te_result,
            "calculations": "OK",
            "message": "Full synkronisering fullført"
        }
        
        sync_jobs[job_id].update({
            "status": "completed", 
            "result": combined_result, 
            "end_time": datetime.now(timezone.utc)
        })
        
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

async def run_calculations_and_caching(job_id: str, db_session: Session, start_date: datetime, end_date: datetime):
    """Kjører alle nødvendige beregninger og caching for raskere datahenting."""
    try:
        from ..services.power_service import PowerService
        from ..services.training_stress_service import TrainingStressService
        
        # 1. Beregn power for alle løpeaktiviteter i perioden
        sync_jobs[job_id]["message"] = "Beregner power for løpeaktiviteter..."
        power_service = PowerService()
        
        # Hent løpeaktiviteter i perioden som mangler power
        from sqlalchemy import and_
        from ..database.models.activity import Activity, ActivityType
        
        running_activities = db_session.query(Activity).join(ActivityType).filter(
            and_(
                Activity.start_time >= start_date,
                Activity.start_time <= end_date,
                ActivityType.type_key == 'running',
                Activity.average_power.is_(None)
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
        training_stress_service = TrainingStressService()
        
        # Hent aktiviteter i perioden som mangler TSS
        activities_without_tss = db_session.query(Activity).filter(
            and_(
                Activity.start_time >= start_date,
                Activity.start_time <= end_date,
                Activity.training_stress_score.is_(None)
            )
        ).all()
        
        tss_calculated = 0
        for activity in activities_without_tss:
            try:
                tss = training_stress_service.calculate_activity_tss(activity, db_session)
                if tss is not None:
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
    Dette inkluderer aktiviteter, FIT-data, helsedata og Training Effect data.
    """
    start_datetime = datetime.combine(request.start_date, datetime.min.time(), tzinfo=timezone.utc)
    end_datetime = datetime.combine(request.end_date, datetime.max.time(), tzinfo=timezone.utc)
    
    job_id = str(uuid.uuid4())
    sync_jobs[job_id] = {"status": "queued", "start_time": datetime.now(timezone.utc)}
    background_tasks.add_task(run_full_sync, job_id, garmin_client, storage, start_datetime, end_datetime)
    
    return {
        "message": f"Full synkronisering startet for perioden {request.start_date} til {request.end_date}. Dette inkluderer aktiviteter, FIT-data, helsedata og Training Effect data.",
        "job_id": job_id
    }

async def run_calculations_only(job_id: str, storage: DataStorage, start_date: datetime, end_date: datetime):
    """Kjører kun beregninger og caching for eksisterende data."""
    db_session = None
    try:
        sync_jobs[job_id]["status"] = "processing"
        sync_jobs[job_id]["message"] = "Starter beregninger og caching..."
        db_session = SessionLocal()
        
        result = await run_calculations_and_caching(job_id, db_session, start_date, end_date)
        
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
    """Kjører synkronisering av nye aktiviteter fra siste lagrede aktivitet."""
    db_session = None
    try:
        sync_jobs[job_id]["status"] = "processing"
        sync_jobs[job_id]["message"] = "Finner siste aktivitet..."
        db_session = SessionLocal()
        
        # Finn siste aktivitet i databasen
        from ..database.models.activity import Activity
        from sqlalchemy import desc
        
        latest_activity = db_session.query(Activity).order_by(desc(Activity.start_time)).first()
        
        if not latest_activity:
            # Ingen aktiviteter i databasen, synkroniser siste 30 dager
            sync_jobs[job_id]["message"] = "Ingen aktiviteter funnet, synkroniserer siste 30 dager..."
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=30)
        else:
            # Bruk datoen for siste aktivitet som startdato
            # Sørg for at start_date har timezone-informasjon
            if latest_activity.start_time.tzinfo is None:
                # Hvis start_time ikke har timezone, anta UTC
                start_date = latest_activity.start_time.replace(tzinfo=timezone.utc)
            else:
                start_date = latest_activity.start_time
            
            end_date = datetime.now(timezone.utc)
            
            sync_jobs[job_id]["message"] = f"Synkroniserer fra {start_date.date()} til {end_date.date()}..."
        
        # Kjør full synkronisering for denne perioden
        sync_service = SyncService(garmin_client, storage, db_session)
        
        # 1. Synkroniser aktiviteter med FIT-data
        sync_jobs[job_id]["message"] = "Synkroniserer aktiviteter..."
        activity_result = await sync_service.sync_activities_with_fit_data(start_date, end_date, True, 100)
        
        # 2. Synkroniser helsedata
        sync_jobs[job_id]["message"] = "Synkroniserer helsedata..."
        await sync_service.sync_health_data(start_date, end_date, True)
        
        # 3. Synkroniser Training Effect data
        sync_jobs[job_id]["message"] = "Synkroniserer Training Effect data..."
        te_result = await sync_service.sync_training_effect_data(start_date, end_date, True)
        
        # 4. Kjør alle beregninger og caching
        sync_jobs[job_id]["message"] = "Kjører beregninger og caching..."
        calc_result = await run_calculations_and_caching(job_id, db_session, start_date, end_date)
        
        # Kombiner resultater
        combined_result = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "activities": activity_result,
            "health_data": "OK",
            "training_effect": te_result,
            "calculations": calc_result,
            "message": "Synkronisering av nye aktiviteter fullført"
        }
        
        sync_jobs[job_id].update({
            "status": "completed", 
            "result": combined_result, 
            "end_time": datetime.now(timezone.utc)
        })
        
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
    
    job_id = str(uuid.uuid4())
    sync_jobs[job_id] = {"status": "queued", "start_time": datetime.now(timezone.utc)}
    background_tasks.add_task(run_calculations_only, job_id, storage, start_datetime, end_datetime)
    
    return {
        "message": f"Beregninger og caching startet for perioden {request.start_date} til {request.end_date}.",
        "job_id": job_id
    }

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
    job_id = str(uuid.uuid4())
    sync_jobs[job_id] = {"status": "queued", "start_time": datetime.now(timezone.utc)}
    background_tasks.add_task(run_new_activities_sync, job_id, garmin_client, storage)
    
    return {
        "message": "Synkronisering av nye aktiviteter startet. Dette vil synkronisere fra siste lagrede aktivitet til nå.",
        "job_id": job_id
    }
