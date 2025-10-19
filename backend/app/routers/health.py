from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import date, datetime, timedelta
import logging
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from ..services.garmin_client import GarminClient
from ..dependencies import get_garmin_client, get_db, get_data_storage
from ..storage import DataStorage
from ..database.models import HRV, Sleep
from ..database.models.sync_state import SyncState

logger = logging.getLogger(__name__)
router = APIRouter()

# Range-endepunkter først (unngå kollisjon med {request_date})

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
    garmin_client: GarminClient = Depends(get_garmin_client),
    db: Session = Depends(get_db)
):
    """Henter HRV-data for en datoperiode med intelligent database-caching. HRV-data er kun tilgjengelig fra 2023 og fremover."""
    logger.info(f"📊 HRV: Forespørsel om HRV-data fra {start_date} til {end_date}")
    if start_date.year < 2023:
        start_date = date(2023, 1, 1)
        logger.info("HRV-startdato justert til 2023-01-01 (HRV-data kun tilgjengelig fra 2023)")
    
    try:
        # 1. Sjekk hvilke datoer som finnes i database
        existing_hrv = db.query(HRV).filter(
            HRV.measurement_date >= start_date,
            HRV.measurement_date <= end_date
        ).all()
        
        existing_dates = {h.measurement_date for h in existing_hrv}
        logger.info(f"💾 HRV: Fant {len(existing_dates)} dager i database")
        
        # 2. Finn manglende datoer
        current = start_date
        missing_dates = []
        while current <= end_date:
            if current not in existing_dates:
                missing_dates.append(current)
            current += timedelta(days=1)
        
        logger.info(f"📥 HRV: {len(missing_dates)} dager mangler, henter fra Garmin...")
        
        # 3. Hent manglende data fra Garmin og lagre i database
        if missing_dates:
            for missing_date in missing_dates:
                try:
                    hrv_data = await garmin_client.get_hrv_data(datetime.combine(missing_date, datetime.min.time()))
                    if hrv_data and hrv_data.get('last_night_avg'):
                        # Lagre i database
                        new_hrv = HRV(
                            measurement_date=missing_date,
                            measurement_time=datetime.combine(missing_date, datetime.min.time()),
                            rmssd=hrv_data.get('last_night_avg'),
                            measurement_type='during_sleep',
                            created_at=datetime.utcnow(),
                            updated_at=datetime.utcnow()
                        )
                        db.add(new_hrv)
                        logger.debug(f"✅ HRV: Lagret data for {missing_date}")
                except Exception as e:
                    logger.debug(f"⚠️ HRV: Ingen data for {missing_date}: {e}")
            
            # Commit alle nye HRV-records
            db.commit()
            logger.info(f"💾 HRV: Lagret nye data i database")
        
        # 4. Hent all data fra database (nå komplett)
        all_hrv = db.query(HRV).filter(
            HRV.measurement_date >= start_date,
            HRV.measurement_date <= end_date
        ).order_by(HRV.measurement_date).all()
        
        # 5. Returner formatert data
        result = []
        for hrv in all_hrv:
            result.append({
                "date": hrv.measurement_date.isoformat(),
                "last_night_avg": hrv.rmssd,
                "measurement_time": hrv.measurement_time.isoformat() if hrv.measurement_time else None,
                "measurement_type": hrv.measurement_type
            })
        
        logger.info(f"✅ HRV: Returnerer {len(result)} dager med data")
        return result
        
    except Exception as e:
        logger.error(f"❌ HRV: Feil ved henting: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Intern serverfeil ved henting av HRV-data.")

@router.get("/body-battery/range", response_model=List[Dict[str, Any]])
async def get_body_battery_range_endpoint(
    start_date: date = Query(..., description="Startdato (YYYY-MM-DD)"),
    end_date: date = Query(..., description="Sluttdato (YYYY-MM-DD)"),
    garmin_client: GarminClient = Depends(get_garmin_client)
):
    """Henter body battery data for en datoperiode."""
    logger.info(f"Mottok forespørsel om body battery data fra {start_date} til {end_date}")
    try:
        start_datetime = datetime.combine(start_date, datetime.min.time())
        end_datetime = datetime.combine(end_date, datetime.min.time())
        body_battery_data = await garmin_client.get_body_battery_range(start_datetime, end_datetime)
        return body_battery_data
    except Exception as e:
        logger.error(f"Feil ved henting av body battery data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Intern serverfeil ved henting av body battery data.")

@router.get("/sleep/range", response_model=List[Dict[str, Any]])
async def get_sleep_range_endpoint(
    start_date: date = Query(..., description="Startdato (YYYY-MM-DD)"),
    end_date: date = Query(..., description="Sluttdato (YYYY-MM-DD)"),
    garmin_client: GarminClient = Depends(get_garmin_client),
    db: Session = Depends(get_db)
):
    """Henter søvndata for en datoperiode med intelligent database-caching."""
    logger.info(f"😴 Søvn: Forespørsel om søvndata fra {start_date} til {end_date}")
    
    try:
        # 1. Sjekk hvilke datoer som finnes i database
        existing_sleep = db.query(Sleep).filter(
            Sleep.sleep_date >= start_date,
            Sleep.sleep_date <= end_date
        ).all()
        
        existing_dates = {s.sleep_date for s in existing_sleep}
        logger.info(f"💾 Søvn: Fant {len(existing_dates)} dager i database")
        
        # 2. Finn manglende datoer
        current = start_date
        missing_dates = []
        while current <= end_date:
            if current not in existing_dates:
                missing_dates.append(current)
            current += timedelta(days=1)
        
        logger.info(f"📥 Søvn: {len(missing_dates)} dager mangler, henter fra Garmin...")
        
        # 3. Hent manglende data fra Garmin og lagre i database
        if missing_dates:
            for missing_date in missing_dates:
                try:
                    sleep_data = await garmin_client.get_sleep_data(datetime.combine(missing_date, datetime.min.time()))
                    if sleep_data and (sleep_data.get('sleep_time') or sleep_data.get('total_sleep')):
                        # Konverter minutter til sekunder
                        def to_sec(minutes_val):
                            if minutes_val is None:
                                return None
                            return float(minutes_val) * 60.0
                        
                        # Lagre i database
                        new_sleep = Sleep(
                            sleep_date=missing_date,
                            total_sleep_time=to_sec(sleep_data.get('sleep_time') or sleep_data.get('total_sleep')),
                            deep_sleep_time=to_sec(sleep_data.get('deep_sleep')),
                            light_sleep_time=to_sec(sleep_data.get('light_sleep')),
                            rem_sleep_time=to_sec(sleep_data.get('rem_sleep')),
                            awake_time=to_sec(sleep_data.get('awake_time')),
                            sleep_score=sleep_data.get('sleep_score'),
                            created_at=datetime.utcnow(),
                            updated_at=datetime.utcnow()
                        )
                        db.add(new_sleep)
                        logger.debug(f"✅ Søvn: Lagret data for {missing_date}")
                except Exception as e:
                    logger.debug(f"⚠️ Søvn: Ingen data for {missing_date}: {e}")
            
            # Commit alle nye søvn-records
            db.commit()
            logger.info(f"💾 Søvn: Lagret nye data i database")
        
        # 4. Hent all data fra database (nå komplett)
        all_sleep = db.query(Sleep).filter(
            Sleep.sleep_date >= start_date,
            Sleep.sleep_date <= end_date
        ).order_by(Sleep.sleep_date).all()
        
        # 5. Returner formatert data (konverter tilbake til minutter)
        result = []
        for sleep in all_sleep:
            result.append({
                "date": sleep.sleep_date.isoformat(),
                "sleep_time": (sleep.total_sleep_time / 60.0) if sleep.total_sleep_time else None,
                "total_sleep": (sleep.total_sleep_time / 60.0) if sleep.total_sleep_time else None,
                "deep_sleep": (sleep.deep_sleep_time / 60.0) if sleep.deep_sleep_time else None,
                "light_sleep": (sleep.light_sleep_time / 60.0) if sleep.light_sleep_time else None,
                "rem_sleep": (sleep.rem_sleep_time / 60.0) if sleep.rem_sleep_time else None,
                "awake_time": (sleep.awake_time / 60.0) if sleep.awake_time else None,
                "sleep_score": sleep.sleep_score
            })
        
        logger.info(f"✅ Søvn: Returnerer {len(result)} dager med data")
        return result
        
    except Exception as e:
        logger.error(f"❌ Søvn: Feil ved henting: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Intern serverfeil ved henting av søvndata.")

# Enkelt-dags endepunkter

@router.get("/stress/{request_date}", response_model=Optional[Dict[str, Any]])
async def get_stress_data_endpoint(
    request_date: date,
    garmin_client: GarminClient = Depends(get_garmin_client)
):
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
    logger.info(f"Mottok forespørsel om HRV-data for {request_date}")
    if request_date.year < 2023:
        raise HTTPException(status_code=400, detail=f"HRV-data er ikke tilgjengelig for {request_date}. HRV-data er kun tilgjengelig fra 2023 og fremover.")
    try:
        hrv_data = await garmin_client.get_hrv_data(request_date)
        if hrv_data is None:
            raise HTTPException(status_code=404, detail="HRV-data ikke funnet.")
        return hrv_data
    except Exception as e:
        logger.error(f"Feil ved henting av hrvdata: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Intern serverfeil ved henting av HRV-data.")

@router.get("/body-battery/{request_date}", response_model=Optional[Dict[str, Any]])
async def get_body_battery_data_endpoint(
    request_date: date,
    garmin_client: GarminClient = Depends(get_garmin_client)
):
    logger.info(f"Mottok forespørsel om body battery data for {request_date}")
    try:
        request_datetime = datetime.combine(request_date, datetime.min.time())
        body_battery_data = await garmin_client.get_body_battery_data(request_datetime)
        if body_battery_data is None:
            raise HTTPException(status_code=404, detail="Body battery data ikke funnet.")
        return body_battery_data
    except Exception as e:
        logger.error(f"Feil ved henting av body battery data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Intern serverfeil ved henting av body battery data.")

@router.get("/sleep/{request_date}", response_model=Optional[Dict[str, Any]])
async def get_sleep_data_endpoint(
    request_date: date,
    garmin_client: GarminClient = Depends(get_garmin_client)
):
    logger.info(f"Mottok forespørsel om søvndata for {request_date}")
    try:
        sleep_data = await garmin_client.get_sleep_data(request_date)
        if sleep_data is None:
            raise HTTPException(status_code=404, detail="Søvndata ikke funnet.")
        return sleep_data
    except Exception as e:
        logger.error(f"Feil ved henting av søvndata: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Intern serverfeil ved henting av søvndata.")

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