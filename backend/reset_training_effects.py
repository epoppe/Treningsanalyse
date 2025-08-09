#!/usr/bin/env python3
"""
Script for å nullstille beregnede Training Effect-verdier slik at vi kan hente faktiske fra Garmin
"""

import os
import sys
import logging
from sqlalchemy import or_

# Legg til app-mappen i Python-stien
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.database.session import SessionLocal
from app.database.models.activity import Activity

# Konfigurer logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def reset_training_effects():
    """Nullstiller alle Training Effect-verdier slik at vi kan hente faktiske fra Garmin"""
    
    db = SessionLocal()
    
    try:
        # Finn alle aktiviteter som har Training Effect-verdier
        activities_with_effects = db.query(Activity).filter(
            or_(
                Activity.total_training_effect.isnot(None),
                Activity.total_anaerobic_training_effect.isnot(None)
            )
        ).all()
        
        logger.info(f"Fant {len(activities_with_effects)} aktiviteter med Training Effect verdier")
        
        if not activities_with_effects:
            logger.info("Ingen aktiviteter har Training Effect verdier å nullstille")
            return
        
        reset_count = 0
        
        for i, activity in enumerate(activities_with_effects, 1):
            logger.info(f"Nullstiller aktivitet {i}/{len(activities_with_effects)}: {activity.activity_id} - {activity.activity_name}")
            
            # Nullstill verdiene
            activity.total_training_effect = None
            activity.total_anaerobic_training_effect = None
            
            reset_count += 1
        
        # Lagre endringene til databasen
        db.commit()
        
        logger.info(f"\n🎉 Fullført! Nullstilt {reset_count} aktiviteter")
        logger.info("Nå kan du kjøre fetch_garmin_training_effects.py for å hente faktiske verdier fra Garmin")
        
    except Exception as e:
        logger.error(f"Feil ved nullstilling av Training Effects: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    logger.info("🚀 Starter nullstilling av beregnede Training Effect verdier...")
    reset_training_effects()
    logger.info("✅ Ferdig!") 