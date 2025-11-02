#!/usr/bin/env python3
"""
Script for å oppdatere eksisterende søvn-records med overall_score fra Garmin
"""
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta

# Add the backend directory to the Python path
sys.path.append(str(Path(__file__).parent))

from app.database.session import SessionLocal
from app.database.models.sleep import Sleep
from app.services.garmin_client import GarminClient
import os
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def update_sleep_overall_scores():
    """Oppdater eksisterende søvn-records med overall_score"""
    # Hent credentials fra environment eller settings
    garmin_email = os.getenv('GARMIN_EMAIL')
    garmin_password = os.getenv('GARMIN_PASSWORD')
    token_dir = os.getenv('TOKEN_DIR', '.garmin_cache')
    
    if not garmin_email or not garmin_password:
        logger.error("GARMIN_EMAIL og GARMIN_PASSWORD må være satt i environment")
        return 0
    
    garmin_client = GarminClient(
        email=garmin_email,
        password=garmin_password,
        token_dir=token_dir
    )
    
    db = SessionLocal()
    
    try:
        # Hent alle søvn-records uten overall_score fra siste 90 dager
        cutoff_date = datetime.now().date() - timedelta(days=90)
        sleep_records = db.query(Sleep).filter(
            Sleep.overall_score.is_(None),
            Sleep.sleep_date >= cutoff_date
        ).order_by(Sleep.sleep_date.desc()).all()
        
        logger.info(f"Fant {len(sleep_records)} søvn-records uten overall_score")
        
        updated = 0
        for sleep_record in sleep_records:
            try:
                # Hent data fra Garmin
                sleep_date = datetime.combine(sleep_record.sleep_date, datetime.min.time())
                sleep_data = await garmin_client.get_sleep_data(sleep_date)
                
                if sleep_data and sleep_data.get('overall_score') is not None:
                    sleep_record.overall_score = sleep_data.get('overall_score')
                    logger.info(f"Oppdatert {sleep_record.sleep_date}: overall_score = {sleep_record.overall_score}")
                    updated += 1
                
                # Rate limiting - vent litt mellom hver forespørsel
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.warning(f"Kunne ikke hente data for {sleep_record.sleep_date}: {e}")
                continue
        
        if updated > 0:
            db.commit()
            logger.info(f"[OK] Oppdatert {updated} søvn-records med overall_score")
        else:
            logger.info("[INFO] Ingen records ble oppdatert")
        
        return updated
        
    except Exception as e:
        logger.error(f"[ERROR] Feil ved oppdatering: {e}", exc_info=True)
        db.rollback()
        return 0
    finally:
        db.close()

if __name__ == "__main__":
    updated_count = asyncio.run(update_sleep_overall_scores())
    sys.exit(0 if updated_count >= 0 else 1)

