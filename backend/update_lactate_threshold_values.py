#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database.session import SessionLocal
from app.database.models.activity import Activity
from app.config import settings
from sqlalchemy import func
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def update_lactate_threshold_values():
    """Oppdaterer alle lactate threshold verdier til fallback-verdien definert i konfigurasjonen."""
    
    db = SessionLocal()
    
    try:
        # Hent alle aktiviteter med lactate threshold
        activities_with_lactate = db.query(Activity).filter(
            Activity.lactate_threshold_speed.isnot(None)
        ).all()
        
        logger.info(f"Fant {len(activities_with_lactate)} aktiviteter med lactate threshold")
        
        if len(activities_with_lactate) == 0:
            logger.info("Ingen aktiviteter med lactate threshold å oppdatere")
            return
        
        # Riktig lactate threshold verdi (default fra config, 5:22 min/km)
        correct_lactate_threshold = settings.LACTATE_THRESHOLD_SPEED
        
        updated_count = 0
        
        for activity in activities_with_lactate:
            current_value = activity.lactate_threshold_speed
            if current_value is None:
                continue

            if abs(current_value - correct_lactate_threshold) > 0.0005:
                activity.lactate_threshold_speed = correct_lactate_threshold
                updated_count += 1
                logger.info(f"Oppdatert aktivitet {activity.activity_id}: {current_value} -> {correct_lactate_threshold}")
        
        # Commit endringene
        db.commit()
        
        logger.info(f"Ferdig! Oppdatert {updated_count} aktiviteter med riktig lactate threshold verdi")
        
        # Verifiser at endringene ble lagret
        activities_with_old_value = db.query(Activity).filter(
            Activity.lactate_threshold_speed.isnot(None),
            func.abs(Activity.lactate_threshold_speed - correct_lactate_threshold) > 0.0005
        ).count()
        
        activities_with_correct_value = db.query(Activity).filter(
            Activity.lactate_threshold_speed == correct_lactate_threshold
        ).count()
        
        logger.info("Verifisering:")
        logger.info(f"- Aktiviteter som fortsatt avviker fra korrekt verdi: {activities_with_old_value}")
        logger.info(f"- Aktiviteter med riktig verdi ({correct_lactate_threshold}): {activities_with_correct_value}")
        
    except Exception as e:
        logger.error(f"Feil under oppdatering: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    print("🚀 Starter oppdatering av lactate threshold verdier...")
    
    update_lactate_threshold_values()
    
    print("✅ Oppdatering fullført") 