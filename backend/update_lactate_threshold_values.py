#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database.session import SessionLocal
from app.database.models.activity import Activity
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def update_lactate_threshold_values():
    """Oppdaterer alle lactate threshold verdier til den riktige verdien (3.11 m/s = 5:21 min/km)."""
    
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
        
        # Riktig lactate threshold verdi (5:21 min/km = 3.11 m/s)
        correct_lactate_threshold = 3.11
        
        updated_count = 0
        
        for activity in activities_with_lactate:
            # Sjekk om verdien er feil (0.347 er den gamle feile verdien)
            if activity.lactate_threshold_speed == 0.347:
                activity.lactate_threshold_speed = correct_lactate_threshold
                updated_count += 1
                logger.info(f"Oppdatert aktivitet {activity.activity_id}: {0.347} -> {correct_lactate_threshold}")
        
        # Commit endringene
        db.commit()
        
        logger.info(f"Ferdig! Oppdatert {updated_count} aktiviteter med riktig lactate threshold verdi")
        
        # Verifiser at endringene ble lagret
        activities_with_old_value = db.query(Activity).filter(
            Activity.lactate_threshold_speed == 0.347
        ).count()
        
        activities_with_correct_value = db.query(Activity).filter(
            Activity.lactate_threshold_speed == correct_lactate_threshold
        ).count()
        
        logger.info(f"Verifisering:")
        logger.info(f"- Aktiviteter med gammel verdi (0.347): {activities_with_old_value}")
        logger.info(f"- Aktiviteter med riktig verdi (3.11): {activities_with_correct_value}")
        
    except Exception as e:
        logger.error(f"Feil under oppdatering: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    print("🚀 Starter oppdatering av lactate threshold verdier...")
    
    update_lactate_threshold_values()
    
    print("✅ Oppdatering fullført") 