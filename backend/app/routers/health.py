from fastapi import APIRouter, Depends, HTTPException
from datetime import date
import logging
from typing import Optional, Dict, Any

from ..services.garmin_client import GarminClient
from ..dependencies import get_garmin_client

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/sleep/{request_date}", response_model=Optional[Dict[str, Any]])
async def get_sleep_data_endpoint(
    request_date: date,
    garmin_client: GarminClient = Depends(get_garmin_client)
):
    """Henter søvndata for en spesifikk dato."""
    logger.info(f"Mottok forespørsel om søvndata for {request_date}")
    try:
        sleep_data = await garmin_client.get_sleep_data(request_date)
        if sleep_data is None:
            raise HTTPException(status_code=404, detail="Søvndata ikke funnet.")
        return sleep_data
    except Exception as e:
        logger.error(f"Feil ved henting av søvndata: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Intern serverfeil ved henting av søvndata.")

@router.get("/stress/{request_date}", response_model=Optional[Dict[str, Any]])
async def get_stress_data_endpoint(
    request_date: date,
    garmin_client: GarminClient = Depends(get_garmin_client)
):
    """Henter stressdata for en spesifikk dato."""
    logger.info(f"Mottok forespørsel om stressdata for {request_date}")
    try:
        stress_data = await garmin_client.get_stress_data(request_date)
        if stress_data is None:
            raise HTTPException(status_code=404, detail="Stressdata ikke funnet.")
        return stress_data
    except Exception as e:
        logger.error(f"Feil ved henting av stressdata: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Intern serverfeil ved henting av stressdata.")

@router.get("/hrv/{request_date}", response_model=Optional[Dict[str, Any]])
async def get_hrv_data_endpoint(
    request_date: date,
    garmin_client: GarminClient = Depends(get_garmin_client)
):
    """Henter HRV-data for en spesifikk dato."""
    logger.info(f"Mottok forespørsel om HRV-data for {request_date}")
    try:
        hrv_data = await garmin_client.get_hrv_data(request_date)
        if hrv_data is None:
            raise HTTPException(status_code=404, detail="HRV-data ikke funnet.")
        return hrv_data
    except Exception as e:
        logger.error(f"Feil ved henting av hrvdata: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Intern serverfeil ved henting av HRV-data.") 