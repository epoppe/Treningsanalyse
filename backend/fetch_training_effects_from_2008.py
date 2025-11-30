#!/usr/bin/env python3
"""
Henter Training Effect data (aerob og anaerob effekt) på nytt for alle aktiviteter fra 2008.
Dette er en engangskjøring som tvinger re-henting av alle verdier.
"""

import sys
import os
import asyncio
from datetime import datetime, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

from app.database.session import SessionLocal
from app.database.models.activity import Activity
from app.services.garmin_client import GarminClient
from app.storage import DataStorage
from app.config import settings
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def fetch_training_effects_from_2008():
    """
    Henter Training Effect data for alle aktiviteter fra 2008 og fremover.
    """
    db = SessionLocal()
    
    try:
        # Initialiser Garmin-klienten
        logger.info("Initialiserer Garmin-klienten...")
        garmin_client = GarminClient(
            email=settings.GARMIN_EMAIL,
            password=settings.GARMIN_PASSWORD,
            token_dir=settings.TOKEN_DIR
        )
        
        success = await garmin_client.initialize()
        if not success:
            logger.error("Kunne ikke initialisere Garmin-klienten")
            return
        
        logger.info("Garmin-klient initialisert")
        
        # Initialiser DataStorage
        storage = DataStorage(settings.DATA_DIR)
        
        # Hent alle aktiviteter fra 2008 og fremover, sortert etter dato (eldste først)
        logger.info("Henter alle aktiviteter fra 2008 og fremover...")
        start_date = datetime(2008, 1, 1, tzinfo=timezone.utc)
        
        activities = db.query(Activity).filter(
            Activity.start_time >= start_date
        ).order_by(Activity.start_time.asc()).all()
        
        logger.info(f"Fant {len(activities)} aktiviteter fra 2008 og fremover")
        
        if not activities:
            logger.warning("Ingen aktiviteter funnet")
            return
        
        # Prosesser aktivitetene
        updated_count = 0
        skipped_count = 0
        failed_count = 0
        
        for i, activity in enumerate(activities, 1):
            activity_id = activity.activity_id
            activity_date = activity.start_time.date()
            
            logger.info(f"Prosesserer aktivitet {i}/{len(activities)}: {activity_id} ({activity_date}) - {activity.activity_name}")
            
            try:
                # Hent Training Effect data fra Garmin
                te_data = await garmin_client.get_activity_training_effect(activity_id)
                
                if te_data:
                    old_aerobic = activity.total_training_effect
                    old_anaerobic = activity.total_anaerobic_training_effect
                    
                    activity.total_training_effect = te_data.get('aerobic_training_effect')
                    activity.total_anaerobic_training_effect = te_data.get('anaerobic_training_effect')
                    
                    # Commit hver 50. aktivitet for å unngå for store transaksjoner
                    if i % 50 == 0:
                        db.commit()
                        logger.info(f"  ✅ Committet {i} aktiviteter så langt...")
                    
                    if old_aerobic != activity.total_training_effect or old_anaerobic != activity.total_anaerobic_training_effect:
                        updated_count += 1
                        logger.info(f"  ✅ Oppdatert: Aerobic={activity.total_training_effect} "
                                  f"(var {old_aerobic}), Anaerobic={activity.total_anaerobic_training_effect} "
                                  f"(var {old_anaerobic})")
                    else:
                        skipped_count += 1
                        logger.debug(f"  ⏭️  Ingen endring: Aerobic={activity.total_training_effect}, "
                                   f"Anaerobic={activity.total_anaerobic_training_effect}")
                else:
                    skipped_count += 1
                    logger.warning(f"  ⚠️  Ingen Training Effect data tilgjengelig for aktivitet {activity_id}")
                    
            except Exception as e:
                failed_count += 1
                logger.error(f"  ❌ Feil ved henting av Training Effect for aktivitet {activity_id}: {e}")
                # Fortsett med neste aktivitet
                continue
        
        # Commit resterende endringer
        db.commit()
        
        logger.info("=" * 80)
        logger.info(f"✅ Ferdig! Oppdatert {updated_count} aktiviteter")
        logger.info(f"   Hoppet over {skipped_count} aktiviteter (ingen endring eller ingen data)")
        logger.info(f"   Feilet {failed_count} aktiviteter")
        logger.info(f"   Totalt prosessert: {len(activities)} aktiviteter")
        
        # Verifiser endringene
        activities_with_te = db.query(Activity).filter(
            Activity.start_time >= start_date,
            (Activity.total_training_effect.isnot(None) | 
             Activity.total_anaerobic_training_effect.isnot(None))
        ).count()
        
        logger.info(f"   Totalt {activities_with_te} aktiviteter har nå Training Effect data")
        
    except Exception as e:
        logger.error(f"Feil ved henting av Training Effect data: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logger.info("🚀 Starter henting av Training Effect data fra 2008...")
    logger.info("📝 Dette kan ta lang tid avhengig av antall aktiviteter...")
    
    asyncio.run(fetch_training_effects_from_2008())
    
    logger.info("✅ Henting fullført!")

