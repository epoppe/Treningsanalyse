#!/usr/bin/env python3
"""
Script for å oppdatere eksisterende HRV-data med baseline-verdier fra Garmin.
"""

import sys
import os
import asyncio
from pathlib import Path
from datetime import datetime, timedelta, date, timezone

# Add the backend directory to the Python path
sys.path.append(str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from app.database.session import SessionLocal
from app.database.models.sleep import HRV
from app.services.garmin_client import GarminClient
from app.config import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def update_hrv_baselines():
    """Oppdaterer eksisterende HRV-records med baseline-verdier."""
    # Initialiser Garmin client
    garmin_client = GarminClient(
        email=settings.GARMIN_EMAIL,
        password=settings.GARMIN_PASSWORD,
        token_dir=settings.TOKEN_DIR
    )
    
    # Initialiser og autentiser
    success = await garmin_client.initialize()
    if not success:
        logger.error("Kunne ikke initialisere Garmin client")
        return False
    
    db = SessionLocal()
    
    try:
        # Få alle HRV-records uten baseline-verdier
        hrv_records = db.query(HRV).filter(
            (HRV.baseline_balanced_lower == None) | 
            (HRV.baseline_balanced_upper == None)
        ).order_by(HRV.measurement_date).all()
        
        logger.info(f"Fant {len(hrv_records)} HRV-records uten baseline-verdier")
        
        if len(hrv_records) == 0:
            logger.info("Alle HRV-records har allerede baseline-verdier")
            return True
        
        updated_count = 0
        for hrv_record in hrv_records:
            try:
                # Hent HRV-data fra Garmin for denne datoen
                hrv_date = datetime.combine(hrv_record.measurement_date, datetime.min.time())
                hrv_data = await garmin_client.get_hrv_data_alternative(hrv_date)
                
                if hrv_data and hrv_data.get('hrv_summary'):
                    hrv_summary = hrv_data.get('hrv_summary', {})
                    
                    # Oppdater baseline-verdier hvis de finnes
                    if hrv_summary.get('baseline_balanced_lower') is not None:
                        hrv_record.baseline_balanced_lower = hrv_summary.get('baseline_balanced_lower')
                    if hrv_summary.get('baseline_balanced_upper') is not None:
                        hrv_record.baseline_balanced_upper = hrv_summary.get('baseline_balanced_upper')
                    if hrv_summary.get('baseline_low_upper') is not None:
                        hrv_record.baseline_low_upper = hrv_summary.get('baseline_low_upper')
                    if hrv_summary.get('status'):
                        hrv_record.status = hrv_summary.get('status')
                    
                    hrv_record.updated_at = datetime.now(timezone.utc)
                    updated_count += 1
                    
                    if updated_count % 10 == 0:
                        db.commit()
                        logger.info(f"Oppdatert {updated_count} records...")
                
                # Ikke spam Garmin API - legg til en liten pause
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.warning(f"Kunne ikke oppdatere HRV for {hrv_record.measurement_date}: {e}")
                continue
        
        # Commit alle endringer
        db.commit()
        logger.info(f"Oppdatert {updated_count} av {len(hrv_records)} HRV-records med baseline-verdier")
        
    except Exception as e:
        logger.error(f"Feil under oppdatering: {e}", exc_info=True)
        db.rollback()
        return False
    finally:
        db.close()
    
    return True

if __name__ == "__main__":
    success = asyncio.run(update_hrv_baselines())
    sys.exit(0 if success else 1)
