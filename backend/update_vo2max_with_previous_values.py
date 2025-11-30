#!/usr/bin/env python3
"""
Oppdaterer VO2 Max-verdier i databasen ved å kopiere forrige gyldige verdi
til aktiviteter som mangler VO2 Max-verdi.
Dette er en engangsoperasjon.
"""

import sys
import os
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

from app.database.session import SessionLocal
from app.database.models.activity import Activity, ActivityType
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def update_vo2max_with_previous_values():
    """
    Oppdaterer alle aktiviteter uten VO2 Max-verdi med forrige gyldige verdi.
    """
    db = SessionLocal()
    
    try:
        # Hent alle løpeaktiviteter sortert etter dato (eldste først)
        logger.info("Henter alle løpeaktiviteter...")
        running_types = db.query(ActivityType).filter(
            ActivityType.type_key.in_(['running', 'treadmill_running'])
        ).all()
        
        running_type_ids = [at.id for at in running_types]
        
        activities = db.query(Activity).filter(
            Activity.activity_type_id.in_(running_type_ids)
        ).order_by(Activity.start_time.asc()).all()
        
        logger.info(f"Fant {len(activities)} løpeaktiviteter")
        
        if not activities:
            logger.warning("Ingen løpeaktiviteter funnet")
            return
        
        # Gå gjennom aktivitetene i kronologisk rekkefølge
        last_valid_vo2max = None
        updated_count = 0
        skipped_count = 0
        
        for activity in activities:
            # Sjekk om aktiviteten er en løpeaktivitet (ikke tredemølle)
            is_running_activity = (
                activity.activity_type and
                activity.activity_type.type_key == 'running' and
                activity.activity_type.type_key != 'treadmill_running'
            )
            
            if not is_running_activity:
                # For tredemølleaktiviteter, hopp over
                continue
            
            # Hvis aktiviteten har en gyldig VO2 Max-verdi, oppdater last_valid_vo2max
            if activity.vo2_max and activity.vo2_max > 0:
                last_valid_vo2max = activity.vo2_max
                logger.debug(
                    f"Aktivitet {activity.activity_id} ({activity.start_time.date()}): "
                    f"Har gyldig VO2 Max: {activity.vo2_max}"
                )
            else:
                # Hvis aktiviteten mangler VO2 Max-verdi, bruk forrige gyldige verdi
                if last_valid_vo2max is not None:
                    old_value = activity.vo2_max
                    activity.vo2_max = last_valid_vo2max
                    updated_count += 1
                    logger.info(
                        f"Oppdatert aktivitet {activity.activity_id} ({activity.start_time.date()}): "
                        f"{old_value} -> {last_valid_vo2max}"
                    )
                else:
                    skipped_count += 1
                    logger.debug(
                        f"Ingen forrige gyldig VO2 Max-verdi for aktivitet {activity.activity_id} "
                        f"({activity.start_time.date()})"
                    )
        
        # Commit endringene
        db.commit()
        
        logger.info(f"✅ Ferdig! Oppdatert {updated_count} aktiviteter med forrige gyldige VO2 Max-verdi")
        logger.info(f"   Hoppet over {skipped_count} aktiviteter (ingen forrige verdi tilgjengelig)")
        
        # Verifiser endringene
        activities_with_vo2max = db.query(Activity).filter(
            Activity.activity_type_id.in_(running_type_ids),
            Activity.vo2_max.isnot(None),
            Activity.vo2_max > 0
        ).count()
        
        logger.info(f"   Totalt {activities_with_vo2max} løpeaktiviteter har nå VO2 Max-verdi")
        
    except Exception as e:
        logger.error(f"Feil ved oppdatering av VO2 Max-verdier: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logger.info("🚀 Starter oppdatering av VO2 Max-verdier...")
    logger.info("📝 Kopierer forrige gyldige verdi til aktiviteter som mangler VO2 Max")
    
    update_vo2max_with_previous_values()
    
    logger.info("✅ Oppdatering fullført!")

