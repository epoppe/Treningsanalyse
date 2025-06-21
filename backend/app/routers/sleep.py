from fastapi import APIRouter, Depends, Query, HTTPException
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Callable, Any
import asyncio
import logging

from ..services.garmin_client import GarminClient
from ..dependencies import get_garmin_client, get_data_storage
from ..storage import DataStorage
from garth.exc import GarthException

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/sleep")
async def get_sleep(
    days: int = Query(7, description="Antall dager å hente data for"),
    force_refresh: bool = Query(False, description="Tving oppdatering fra Garmin Connect"),
    garmin_client: GarminClient = Depends(get_garmin_client),
    storage: DataStorage = Depends(get_data_storage)
):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    return await get_data_with_caching(
        storage_get_method=storage.get_sleep_data,
        storage_save_method=storage.save_sleep_data,
        garmin_fetch_method=garmin_client.get_sleep_data,
        fetch_args={"start_date": start_date, "end_date": end_date},
        force_refresh=force_refresh,
        garmin_client=garmin_client,
        storage=storage,
        data_key_plural="søvndata",
        response_data_key="sleep_data"
    )

async def get_data_with_caching(
    storage_get_method: Callable[..., List[Dict[str, Any]]],
    storage_save_method: Callable[[List[Dict[str, Any]]], None],
    garmin_fetch_method: Callable[..., asyncio.Future[List[Dict[str, Any]]]],
    fetch_args: Dict[str, Any],
    force_refresh: bool,
    garmin_client: GarminClient,
    storage: DataStorage,
    data_key_plural: str,
    response_data_key: str
) -> Dict[str, Any]:
    
    if not garmin_client.is_authenticated():
        logger.warning(f"Garmin-klient ikke autentisert. Returnerer kun lokale {data_key_plural}.")
        local_data = storage_get_method(**fetch_args)
        return {
            response_data_key: local_data if local_data else [],
            "count": len(local_data) if local_data else 0,
            "period": {
                "start": fetch_args['start_date'].strftime("%Y-%m-%d"),
                "end": fetch_args['end_date'].strftime("%Y-%m-%d")
            },
            "source": "local_only",
            "warning": "Garmin Connect ikke tilgjengelig. Viser kun lokale data."
        }
    
    local_data = storage_get_method(**fetch_args)

    if local_data and not force_refresh:
        logger.info(f"Returnerer {data_key_plural} fra lokal database")
        return {
            response_data_key: local_data,
            "count": len(local_data),
            "period": {
                "start": fetch_args['start_date'].strftime("%Y-%m-%d"),
                "end": fetch_args['end_date'].strftime("%Y-%m-%d")
            },
            "source": "local"
        }
    
    try:
        logger.info(f"Henter {data_key_plural} fra Garmin Connect")
        new_data = await garmin_fetch_method(**fetch_args)
        
        if new_data:
            storage_save_method(new_data)
            logger.info(f"{len(new_data)} {data_key_plural} lagret i lokal database.")
        else:
            logger.info(f"Ingen nye {data_key_plural} mottatt fra Garmin Connect.")

        return {
            response_data_key: new_data if new_data else [],
            "count": len(new_data) if new_data else 0,
            "period": {
                "start": fetch_args['start_date'].strftime("%Y-%m-%d"),
                "end": fetch_args['end_date'].strftime("%Y-%m-%d")
            },
            "source": "garmin"
        }
        
    except GarthException as ge:
        logger.error(f"Garmin API feil under henting av {data_key_plural}: {ge}", exc_info=True)
        if "429" in str(ge) or (hasattr(ge, 'response') and ge.response is not None and ge.response.status_code == 429):
            local_data = storage_get_method(**fetch_args)
            return {
                response_data_key: local_data if local_data else [],
                "count": len(local_data) if local_data else 0,
                "period": {
                    "start": fetch_args['start_date'].strftime("%Y-%m-%d"),
                    "end": fetch_args['end_date'].strftime("%Y-%m-%d")
                },
                "source": "local_fallback",
                "warning": "Rate-limit nådd for Garmin Connect. Viser lokale data."
            }
        raise HTTPException(status_code=503, detail=f"Feil ved kommunikasjon med Garmin Connect for {data_key_plural}: {str(ge)}")
    except Exception as e:
        logger.error(f"Uventet feil under henting av {data_key_plural}: {e}", exc_info=True)
        local_data = storage_get_method(**fetch_args)
        if local_data:
            return {
                response_data_key: local_data,
                "count": len(local_data),
                "period": {
                    "start": fetch_args['start_date'].strftime("%Y-%m-%d"),
                    "end": fetch_args['end_date'].strftime("%Y-%m-%d")
                },
                "source": "local_fallback",
                "warning": f"Feil ved henting fra Garmin Connect. Viser lokale data. Feil: {str(e)}"
            }
        raise HTTPException(status_code=500, detail=f"En intern feil oppstod ved henting av {data_key_plural}: {str(e)}")
