import os
import sys
import logging
from sqlalchemy.orm import Session
from pathlib import Path

# Legg til rotmappen i sys.path for å kunne importere app-moduler
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from app.database.session import get_db
from app.database.models.activity import Activity, ActivityType
from app.services.analysis_service import AnalysisService
from app.storage import DataStorage
from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def precompute_body_battery():
    """
    Forhåndsberegner og cacher Body Battery for aktiviteter.
    """
    storage = DataStorage(settings.DATA_DIR)
    analysis_service = AnalysisService(storage)
    db_session_gen = get_db()
    
    try:
        db: Session = next(db_session_gen)
        logger.info("Starter forhåndsberegning av Body Battery...")

        # Hent alle aktiviteter som mangler Body Battery
        activities_to_process = db.query(Activity).filter(
            Activity.body_battery_start == None
        ).order_by(Activity.start_time.desc()).all()
        
        total_activities = len(activities_to_process)
        logger.info(f"Fant {total_activities} aktiviteter som skal prosesseres.")

        successful_calculations = 0
        failed_calculations = 0

        for i, activity in enumerate(activities_to_process):
            logger.info(f"Prosesserer aktivitet {i+1}/{total_activities}: {activity.activity_id}")
            
            try:
                result = analysis_service.calculate_body_battery_start(int(activity.activity_id), db)
                if result:
                    successful_calculations += 1
                    logger.info(f"✓ Body Battery beregnet for aktivitet {activity.activity_id}: {result['body_battery_start']}")
                else:
                    failed_calculations += 1
                    logger.warning(f"✗ Kunne ikke beregne Body Battery for aktivitet {activity.activity_id}")
                    # Sett til spesiell verdi for å unngå å prøve igjen
                    activity.body_battery_start = -1.0
                    db.commit()
            except Exception as e:
                failed_calculations += 1
                logger.warning(f"✗ Feil ved beregning av Body Battery for {activity.activity_id}: {e}")
                # Sett til spesiell verdi for å unngå å prøve igjen
                activity.body_battery_start = -1.0
                db.commit()
        
        logger.info("Forhåndsberegning av Body Battery fullført.")
        logger.info(f"Resultat: {successful_calculations} vellykket, {failed_calculations} feilet")

    except Exception as e:
        logger.error(f"En feil oppstod under forhåndsberegning: {e}")
    finally:
        # Sørg for at database-sesjonen lukkes
        if 'db' in locals() and db.is_active:
            db.close()

if __name__ == "__main__":
    precompute_body_battery() 