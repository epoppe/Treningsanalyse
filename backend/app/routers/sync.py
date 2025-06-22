from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from datetime import date, datetime, timezone
import logging
from sqlalchemy.orm import Session
import pytz
import asyncio
from fastapi import status

from ..services.garmin_client import GarminClient
from ..storage import DataStorage
from ..services.sync_service import SyncService
from ..dependencies import get_garmin_client, get_data_storage, get_db
from ..database.session import SessionLocal
from garth.exc import GarthException
from ..config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

class SyncRequest(BaseModel):
    start_date: date
    end_date: date

async def run_sync(garmin_client: GarminClient, storage: DataStorage, start_date: datetime, end_date: datetime):
    """
    Hjelpefunksjon for å kjøre synkroniseringen i bakgrunnen med sin egen DB-sesjon.
    """
    db_session = None
    try:
        db_session = SessionLocal()
        sync_service = SyncService(garmin_client, storage, db_session)
        await sync_service.sync_activities(start_date, end_date)
    except Exception as e:
        logger.critical(f"En feil oppstod i bakgrunnssynken: {e}", exc_info=True)
    finally:
        if db_session:
            db_session.close()

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

@router.post("/sync/activities", status_code=202)
async def trigger_activity_sync(
    request: SyncRequest,
    background_tasks: BackgroundTasks,
    storage: DataStorage = Depends(get_data_storage),
    garmin_client: GarminClient = Depends(get_garmin_client)
):
    """
    Starter en bakgrunnsjobb for å synkronisere aktiviteter for en gitt tidsperiode.
    """
    logger.info(f"Mottok synkroniseringsforespørsel med datoer: start_date={request.start_date}, end_date={request.end_date}")
    
    # Konverter date til datetime med UTC tidssone for intern bruk
    start_datetime = datetime.combine(request.start_date, datetime.min.time(), tzinfo=timezone.utc)
    end_datetime = datetime.combine(request.end_date, datetime.max.time(), tzinfo=timezone.utc)
    
    logger.info(f"Konverterte datoer til datetime: start_datetime={start_datetime}, end_datetime={end_datetime}")

    # Legg til synkroniseringsjobben i bakgrunnen
    # Service blir nå opprettet inne i run_sync med egen db-sesjon
    background_tasks.add_task(run_sync, garmin_client, storage, start_datetime, end_datetime)
    
    return {"message": "Synkronisering av aktiviteter er startet i bakgrunnen."}

@router.post("/sync/historical/{start_year}")
async def sync_historical_data(
    start_year: int, 
    garmin_client: GarminClient = Depends(get_garmin_client),
    storage: DataStorage = Depends(get_data_storage)
):
    """Start synkronisering av historiske data (aktiviteter og søvn) fra et gitt år."""
    try:
        if start_year < 2010 or start_year > datetime.now().year:
            raise HTTPException(
                status_code=400,
                detail=f"Start-år må være mellom 2010 og {datetime.now().year}"
            )
        
        logger.info(f"Starter historisk datasynkroniseringsjobb for år {start_year} via API-endepunkt.")

        sync_result = await garmin_client.sync_historical_data(start_year)

        activities_to_save = sync_result.get("all_activities", [])
        sleep_entries_to_save = sync_result.get("all_sleep_entries", [])

        if activities_to_save:
            logger.info(f"Lagrer {len(activities_to_save)} aktiviteter fra historisk synkronisering for {start_year}.")
            storage.save_activities(activities_to_save)
        else:
            logger.info(f"Ingen nye aktiviteter å lagre fra historisk synkronisering for {start_year}.")

        if sleep_entries_to_save:
            logger.info(f"Lagrer {len(sleep_entries_to_save)} søvnregistreringer fra historisk synkronisering for {start_year}.")
            storage.save_sleep_data(sleep_entries_to_save)
        else:
            logger.info(f"Ingen nye søvnregistreringer å lagre fra historisk synkronisering for {start_year}.")

        response_stats = {
            "year": sync_result.get("year"),
            "total_activities_synced": sync_result.get("total_activities_synced"),
            "total_sleep_entries_synced": sync_result.get("total_sleep_entries_synced")
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

@router.post("/activities", status_code=status.HTTP_202_ACCEPTED)
async def sync_activities_endpoint(
    sync_request: SyncRequest,
    background_tasks: BackgroundTasks,
    garmin_client: GarminClient = Depends(get_garmin_client),
):
    start_date = sync_request.start_date
    end_date = sync_request.end_date
    
    logger.info(f"Mottok synkroniseringsforespørsel med datoer: start_date={start_date}, end_date={end_date}")

    # Konverter til datetime-objekter med tidssone for Garmin-klienten
    start_datetime = pytz.utc.localize(datetime.combine(start_date, datetime.min.time()))
    end_datetime = pytz.utc.localize(datetime.combine(end_date, datetime.max.time()))
    logger.info(f"Konverterte datoer til datetime: start_datetime={start_datetime}, end_datetime={end_datetime}")

    def run_sync():
        db_session = SessionLocal()
        try:
            # DataStorage-instansen trengs, men er ikke lenger primærlageret for synk mot DB.
            # Gi den en gyldig mappe for å unngå feil ved initialisering.
            storage = DataStorage(data_dir=settings.DATA_DIR) 
            sync_service = SyncService(garmin_client, storage, db_session)
            asyncio.run(sync_service.sync_activities(start_datetime, end_datetime))
        finally:
            db_session.close()

    background_tasks.add_task(run_sync)
    
    return {"message": "Activity synchronization started in the background."}

@router.post("/sync-json-to-db", status_code=status.HTTP_200_OK)
def sync_json_to_db_endpoint(db: Session = Depends(get_db)):
    """
    Et endepunkt for manuelt å trigge synkronisering fra JSON-filer til databasen.
    """
    # Denne funksjonen er nå mindre relevant, men beholdes for eventuell fremtidig bruk.
    sync_service = SyncService(None, get_data_storage(), db) # GarminClient er ikke nødvendig her
    result = sync_service.sync_json_to_db()
    return result
