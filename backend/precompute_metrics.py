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

def precompute_metrics():
    """
    Forhåndsberegner og cacher decoupling og negative split for løpeaktiviteter.
    """
    storage = DataStorage(settings.DATA_DIR)
    analysis_service = AnalysisService(storage)
    db_session_gen = get_db()
    
    try:
        db: Session = next(db_session_gen)
        logger.info("Starter forhåndsberegning av beregningsverdier...")

        # Hent ID for løpingstypen
        running_type = db.query(ActivityType).filter(ActivityType.type_key == 'running').first()
        if not running_type:
            logger.error("Aktivitetstypen 'running' ble ikke funnet. Avslutter.")
            return

        # Hent alle løpeaktiviteter som mangler enten decoupling eller negative split
        activities_to_process = db.query(Activity).filter(
            Activity.activity_type_id == running_type.id,
            (Activity.decoupling_percent == None) | (Activity.negative_split_percent == None)
        ).all()
        
        total_activities = len(activities_to_process)
        logger.info(f"Fant {total_activities} løpeaktiviteter som skal prosesseres.")

        for i, activity in enumerate(activities_to_process):
            logger.info(f"Prosesserer aktivitet {i+1}/{total_activities}: {activity.activity_id}")
            
            # Beregn og cache decoupling
            if activity.decoupling_percent is None:
                try:
                    analysis_service.calculate_decoupling(int(activity.activity_id), db)
                except Exception as e:
                    logger.warning(f"Kunne ikke beregne decoupling for {activity.activity_id}: {e}")
                    # Sett til en spesiell verdi (f.eks. -1) for å unngå å prøve igjen
                    activity.decoupling_percent = -1.0 
                    db.commit()


            # Beregn og cache negative split
            if activity.negative_split_percent is None:
                try:
                    analysis_service.calculate_negative_split(int(activity.activity_id), db)
                except Exception as e:
                    logger.warning(f"Kunne ikke beregne negativ split for {activity.activity_id}: {e}")
                    activity.negative_split_percent = -1.0
                    db.commit()
        
        logger.info("Forhåndsberegning fullført.")

    except Exception as e:
        logger.error(f"En feil oppstod under forhåndsberegning: {e}")
    finally:
        # Sørg for at database-sesjonen lukkes
        if 'db' in locals() and db.is_active:
            db.close()

if __name__ == "__main__":
    precompute_metrics() 