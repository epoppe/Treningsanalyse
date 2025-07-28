#!/usr/bin/env python3

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database.session import SessionLocal
from app.database.models.activity import Activity
from app.services.garmin_client import GarminClient
from app.config import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def sync_lactate_threshold_for_all_activities():
    """Synkroniser lactate threshold for alle aktiviteter som mangler det."""
    
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
        return
    
    db = SessionLocal()
    
    try:
        # Hent alle aktiviteter uten lactate threshold
        activities_without_lactate = db.query(Activity).filter(
            Activity.lactate_threshold_speed.is_(None)
        ).order_by(Activity.start_time.desc()).all()
        
        logger.info(f"Fant {len(activities_without_lactate)} aktiviteter uten lactate threshold")
        
        if len(activities_without_lactate) == 0:
            logger.info("Alle aktiviteter har lactate threshold")
            return
        
        # Bruk fallback lactate threshold fra config
        fallback_lactate_threshold = settings.LACTATE_THRESHOLD_SPEED
        logger.info(f"Bruker fallback lactate threshold: {fallback_lactate_threshold} m/s")
        
        updated_count = 0
        
        for activity in activities_without_lactate:
            try:
                # Prøv å hente lactate threshold fra Garmin
                lactate_threshold = await garmin_client.get_lactate_threshold_speed()
                
                if lactate_threshold is None:
                    # Bruk fallback hvis Garmin ikke returnerer noe
                    lactate_threshold = fallback_lactate_threshold
                    logger.info(f"Aktivitet {activity.activity_id}: Bruker fallback lactate threshold")
                else:
                    logger.info(f"Aktivitet {activity.activity_id}: Hentet lactate threshold fra Garmin: {lactate_threshold}")
                
                # Oppdater aktiviteten
                activity.lactate_threshold_speed = lactate_threshold
                updated_count += 1
                
                # Commit hver 100. aktivitet for å unngå for store transaksjoner
                if updated_count % 100 == 0:
                    db.commit()
                    logger.info(f"Oppdatert {updated_count} aktiviteter så langt...")
                
            except Exception as e:
                logger.error(f"Feil ved oppdatering av aktivitet {activity.activity_id}: {e}")
                # Bruk fallback hvis det oppstår feil
                activity.lactate_threshold_speed = fallback_lactate_threshold
                updated_count += 1
        
        # Commit resterende endringer
        db.commit()
        
        logger.info(f"Ferdig! Oppdatert {updated_count} aktiviteter med lactate threshold")
        
    except Exception as e:
        logger.error(f"Feil under synkronisering: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(sync_lactate_threshold_for_all_activities()) 