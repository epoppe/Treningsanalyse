from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import date, datetime, timedelta
import logging
from typing import Optional, Dict, Any, List

from ..services.garmin_client import GarminClient
from ..dependencies import get_garmin_client

logger = logging.getLogger(__name__)
router = APIRouter()

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
    """Henter HRV-data for en spesifikk dato. HRV-data er kun tilgjengelig fra 2023 og fremover."""
    logger.info(f"Mottok forespørsel om HRV-data for {request_date}")
    
    # HRV-data er kun tilgjengelig fra 2023 og fremover
    if request_date.year < 2023:
        raise HTTPException(
            status_code=400, 
            detail=f"HRV-data er ikke tilgjengelig for {request_date}. HRV-data er kun tilgjengelig fra 2023 og fremover."
        )
    
    try:
        hrv_data = await garmin_client.get_hrv_data(request_date)
        if hrv_data is None:
            raise HTTPException(status_code=404, detail="HRV-data ikke funnet.")
        return hrv_data
    except Exception as e:
        logger.error(f"Feil ved henting av hrvdata: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Intern serverfeil ved henting av HRV-data.")

# Nye endpoints basert på Garmy metrics

@router.get("/body-battery/{request_date}", response_model=Optional[Dict[str, Any]])
async def get_body_battery_data_endpoint(
    request_date: date,
    garmin_client: GarminClient = Depends(get_garmin_client)
):
    """Henter body battery data for en spesifikk dato."""
    logger.info(f"Mottok forespørsel om body battery data for {request_date}")
    try:
        # Konverter date til datetime
        request_datetime = datetime.combine(request_date, datetime.min.time())
        body_battery_data = await garmin_client.get_body_battery_data(request_datetime)
        if body_battery_data is None:
            raise HTTPException(status_code=404, detail="Body battery data ikke funnet.")
        return body_battery_data
    except Exception as e:
        logger.error(f"Feil ved henting av body battery data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Intern serverfeil ved henting av body battery data.")

@router.get("/body-battery/range", response_model=List[Dict[str, Any]])
async def get_body_battery_range_endpoint(
    start_date: date = Query(..., description="Startdato (YYYY-MM-DD)"),
    end_date: date = Query(..., description="Sluttdato (YYYY-MM-DD)"),
    garmin_client: GarminClient = Depends(get_garmin_client)
):
    """Henter body battery data for en datoperiode."""
    logger.info(f"Mottok forespørsel om body battery data fra {start_date} til {end_date}")
    try:
        # Konverter date til datetime
        start_datetime = datetime.combine(start_date, datetime.min.time())
        end_datetime = datetime.combine(end_date, datetime.min.time())
        body_battery_data = await garmin_client.get_body_battery_range(start_datetime, end_datetime)
        return body_battery_data
    except Exception as e:
        logger.error(f"Feil ved henting av body battery data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Intern serverfeil ved henting av body battery data.")

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

@router.get("/sleep/range", response_model=List[Dict[str, Any]])
async def get_sleep_range_endpoint(
    start_date: date = Query(..., description="Startdato (YYYY-MM-DD)"),
    end_date: date = Query(..., description="Sluttdato (YYYY-MM-DD)"),
    garmin_client: GarminClient = Depends(get_garmin_client)
):
    """Henter søvndata for en datoperiode."""
    logger.info(f"Mottok forespørsel om søvndata fra {start_date} til {end_date}")
    try:
        sleep_data = await garmin_client.get_sleep_range(start_date, end_date)
        return sleep_data
    except Exception as e:
        logger.error(f"Feil ved henting av søvndata: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Intern serverfeil ved henting av søvndata.")

@router.get("/stress/range", response_model=List[Dict[str, Any]])
async def get_stress_range_endpoint(
    start_date: date = Query(..., description="Startdato (YYYY-MM-DD)"),
    end_date: date = Query(..., description="Sluttdato (YYYY-MM-DD)"),
    garmin_client: GarminClient = Depends(get_garmin_client)
):
    """Henter stressdata for en datoperiode."""
    logger.info(f"Mottok forespørsel om stressdata fra {start_date} til {end_date}")
    try:
        stress_data = await garmin_client.get_stress_range(start_date, end_date)
        return stress_data
    except Exception as e:
        logger.error(f"Feil ved henting av stressdata: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Intern serverfeil ved henting av stressdata.")

@router.get("/hrv/range", response_model=List[Dict[str, Any]])
async def get_hrv_range_endpoint(
    start_date: date = Query(..., description="Startdato (YYYY-MM-DD)"),
    end_date: date = Query(..., description="Sluttdato (YYYY-MM-DD)"),
    garmin_client: GarminClient = Depends(get_garmin_client)
):
    """Henter HRV-data for en datoperiode. HRV-data er kun tilgjengelig fra 2023 og fremover."""
    logger.info(f"Mottok forespørsel om HRV-data fra {start_date} til {end_date}")
    
    # HRV-data er kun tilgjengelig fra 2023 og fremover
    if start_date.year < 2023:
        start_date = date(2023, 1, 1)
        logger.info(f"HRV-startdato justert til 2023-01-01 (HRV-data kun tilgjengelig fra 2023)")
    
    try:
        hrv_data = await garmin_client.get_hrv_range(start_date, end_date)
        return hrv_data
    except Exception as e:
        logger.error(f"Feil ved henting av HRV-data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Intern serverfeil ved henting av HRV-data.")

@router.get("/metrics/summary")
async def get_metrics_summary_endpoint(
    date: date = Query(..., description="Dato for sammendrag (YYYY-MM-DD)"),
    garmin_client: GarminClient = Depends(get_garmin_client)
):
    """Henter et sammendrag av alle tilgjengelige metrics for en dato."""
    logger.info(f"Mottok forespørsel om metrics sammendrag for {date}")
    try:
        summary = await garmin_client.get_daily_metrics_summary(date)
        return summary
    except Exception as e:
        logger.error(f"Feil ved henting av metrics sammendrag: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Intern serverfeil ved henting av metrics sammendrag.") 