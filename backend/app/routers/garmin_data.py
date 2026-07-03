from fastapi import APIRouter, Query, Depends, HTTPException
from datetime import date, datetime, timedelta, timezone
from sqlalchemy.orm import Session
from ..services.garmin_client import GarminClient
from ..dependencies import get_garmin_client, get_db
from ..database.models.activity import GarminPerformanceMetric
import asyncio
from typing import Optional
from ..services.garmin_auth import (
    GarminAuthError,
    GarminRateLimitError,
    GarminReauthRequiredError,
)
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/garmin-performance")
async def get_garmin_performance_metrics(
    start_date: date = Query(..., description="Startdato YYYY-MM-DD"),
    end_date: date = Query(..., description="Sluttdato YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """Hent lagrede Garmin VO2max/status/load/endurance/hill-metrikker fra databasen."""
    start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)
    rows = (
        db.query(GarminPerformanceMetric)
        .filter(GarminPerformanceMetric.date >= start_dt)
        .filter(GarminPerformanceMetric.date <= end_dt)
        .order_by(GarminPerformanceMetric.date)
        .all()
    )
    return [
        {
            column.name: getattr(row, column.name)
            for column in GarminPerformanceMetric.__table__.columns
        }
        for row in rows
    ]

@router.get("/heart-rate")
async def get_heart_rate(date: Optional[str] = None, garmin_client: GarminClient = Depends(get_garmin_client)):
    """Hent pulsdata fra Garmin Connect."""
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d") if date else datetime.now()
        heart_rate_data = await garmin_client.get_heart_rate_data(target_date)
        
        return {
            "date": target_date.strftime("%Y-%m-%d"),
            "heart_rate": heart_rate_data
        }

    except GarminRateLimitError as ge:
        logger.error(f"Garmin rate limit under henting av pulsdata: {ge}", exc_info=True)
        raise HTTPException(
            status_code=429,
            detail="For mange forespørsler til Garmin Connect. Vennligst vent litt og prøv igjen."
        )
    except GarminReauthRequiredError as ge:
        logger.error(f"Garmin krever ny innlogging under henting av pulsdata: {ge}", exc_info=True)
        raise HTTPException(status_code=503, detail=f"Garmin krever ny innlogging: {str(ge)}")
    except GarminAuthError as ge:
        logger.error(f"Garmin API feil under henting av pulsdata: {ge}", exc_info=True)
        raise HTTPException(status_code=503, detail=f"Feil ved kommunikasjon med Garmin Connect: {str(ge)}")
    except ValueError:
        raise HTTPException(status_code=400, detail="Ugyldig datoformat. Bruk YYYY-MM-DD.")
    except Exception as e:
        logger.error(f"Uventet feil under henting av pulsdata: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"En intern feil oppstod: {str(e)}")

@router.get("/resting-heart-rate/{date}")
async def get_resting_heart_rate(date: str, garmin_client: GarminClient = Depends(get_garmin_client)):
    """Hent hvilepulsdata for en spesifikk dato."""
    try:
        date_obj = datetime.strptime(date, "%Y-%m-%d")
        return await garmin_client.get_resting_heart_rate_data(date_obj)
    except ValueError:
        raise HTTPException(status_code=400, detail="Ugyldig datoformat. Bruk YYYY-MM-DD")
    except GarminRateLimitError as ge:
        logger.error(f"Garmin rate limit under henting av hvilepuls: {ge}", exc_info=True)
        raise HTTPException(
            status_code=429,
            detail="For mange forespørsler til Garmin Connect. Vennligst vent litt og prøv igjen."
        )
    except GarminReauthRequiredError as ge:
        logger.error(f"Garmin krever ny innlogging under henting av hvilepuls: {ge}", exc_info=True)
        raise HTTPException(status_code=503, detail=f"Garmin krever ny innlogging: {str(ge)}")
    except GarminAuthError as ge:
        logger.error(f"Garmin API feil under henting av hvilepuls: {ge}", exc_info=True)
        raise HTTPException(status_code=503, detail=f"Feil ved kommunikasjon med Garmin Connect: {str(ge)}")
    except Exception as e:
        logger.error(f"Uventet feil under henting av hvilepuls: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"En intern feil oppstod: {str(e)}")

@router.get("/training-status")
async def get_training_status(
    days: int = Query(7, description="Antall dager å hente data for"),
    garmin_client: GarminClient = Depends(get_garmin_client)
):
    """
    Henter treningsstatus data fra Garmin Connect.
    Inkluderer status, belastning, VO2max, restitusjonsbehov, treningseffekt og mer.
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    return await garmin_client.get_training_status(start_date, end_date) 

@router.get("/all")
async def get_all_data(
    days: int = Query(7, description="Antall dager å hente data for"),
    garmin_client: GarminClient = Depends(get_garmin_client)
):
    """
    Henter alle tilgjengelige data fra Garmin Connect.
    Inkluderer aktiviteter, puls, stress, og treningsstatus.
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    # Hent alle datatyper parallelt
    activities_task = garmin_client.get_activities(start_date, end_date)
    
    heart_rate_task = garmin_client.get_heart_rate_data(start_date, end_date)
    stress_task = garmin_client.get_stress_data(start_date, end_date)
    training_status_task = garmin_client.get_training_status(start_date, end_date)
    
    # Vent på at alle oppgaver er ferdige
    results = await asyncio.gather(
        activities_task,
        heart_rate_task,
        stress_task,
        training_status_task,
        return_exceptions=True
    )
    
    # Pakk ut resultatene
    activities_data, heart_rate_data, stress_data, training_status_data = results
    
    return {
        "aktiviteter": activities_data.get("activities", []) if isinstance(activities_data, dict) else [],
        "puls": heart_rate_data.get("pulsdata", []) if isinstance(heart_rate_data, dict) else [],
        "stress": stress_data.get("stress", []) if isinstance(stress_data, dict) else [],
        "treningsstatus": training_status_data.get("treningsstatus", []) if isinstance(training_status_data, dict) else [],
        "periode": {
            "fra": start_date.strftime("%Y-%m-%d"),
            "til": end_date.strftime("%Y-%m-%d")
        }
    } 
