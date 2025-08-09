#!/usr/bin/env python3
"""
Script for å hente Training Effect data fra Garmin for alle aktiviteter som mangler det
"""

import asyncio
import logging
from datetime import datetime, timedelta
from app.services.garmin_client import GarminClient
from app.database.session import SessionLocal
from app.database.models.activity import Activity
from app.config import settings
from sqlalchemy import desc, or_

# Konfigurer logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def fetch_all_training_effects():
    """Henter Training Effect data fra Garmin for alle aktiviteter som mangler det"""
    
    garmin_client = GarminClient(
        email=settings.GARMIN_EMAIL,
        password=settings.GARMIN_PASSWORD,
        token_dir=settings.TOKEN_DIR
    )
    
    db = SessionLocal()
    
    try:
        # Initialiser Garmin-klient
        if not await garmin_client.initialize():
            logger.error("❌ Kunne ikke autentisere med Garmin")
            return
        
        logger.info("✅ Autentisert med Garmin")
        
        # Finn alle aktiviteter som mangler Training Effect verdier
        activities_without_effects = db.query(Activity).filter(
            or_(
                Activity.total_training_effect.is_(None),
                Activity.total_anaerobic_training_effect.is_(None)
            )
        ).order_by(desc(Activity.start_time)).all()
        
        logger.info(f"📊 Fant {len(activities_without_effects)} aktiviteter som mangler Training Effect verdier")
        
        if not activities_without_effects:
            logger.info("Alle aktiviteter har allerede Training Effect verdier")
            return
        
        updated_count = 0
        failed_count = 0
        skipped_count = 0
        
        for i, activity in enumerate(activities_without_effects, 1):
            activity_id = activity.activity_id
            logger.info(f"Prosesserer aktivitet {i}/{len(activities_without_effects)}: {activity_id} - {activity.activity_name}")
            
            try:
                # Hent Training Effect data fra Garmin
                te_data = await garmin_client.get_activity_training_effect(activity_id)
                
                if te_data:
                    # Oppdater aktiviteten med faktiske verdier fra Garmin
                    activity.total_training_effect = te_data.get('aerobic_training_effect')
                    activity.total_anaerobic_training_effect = te_data.get('anaerobic_training_effect')
                    
                    logger.info(f"✅ Oppdatert aktivitet {activity_id}: "
                              f"Aerobic={activity.total_training_effect}, "
                              f"Anaerobic={activity.total_anaerobic_training_effect}")
                    
                    if te_data.get('training_effect_label'):
                        logger.info(f"    🏷️  Label: {te_data['training_effect_label']}")
                    
                    updated_count += 1
                else:
                    logger.info(f"    ⚠️  Ingen Training Effect data funnet for aktivitet {activity_id}")
                    skipped_count += 1
                
                # Liten pause for å unngå rate limiting
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"❌ Feil ved henting av Training Effect for aktivitet {activity_id}: {e}")
                failed_count += 1
        
        # Lagre endringene til databasen
        db.commit()
        
        logger.info(f"\n🎉 Fullført! Oppdatert {updated_count} aktiviteter, {skipped_count} hoppet over, {failed_count} feilet")
        
        # Vis et sammendrag av de oppdaterte verdiene
        logger.info(f"\n📊 SAMMENDRAG AV OPPDATERTE VERDIER:")
        for activity in activities_without_effects[:10]:  # Vis første 10
            if activity.total_training_effect or activity.total_anaerobic_training_effect:
                logger.info(f"  {activity.activity_id}: Aerobic={activity.total_training_effect}, "
                           f"Anaerobic={activity.total_anaerobic_training_effect}")
        
        if len(activities_without_effects) > 10:
            logger.info(f"  ... og {len(activities_without_effects) - 10} flere aktiviteter")
        
    except Exception as e:
        logger.error(f"Feil ved henting av Training Effects: {e}")
        db.rollback()
        import traceback
        traceback.print_exc()
    
    finally:
        db.close()

if __name__ == "__main__":
    logger.info("🚀 Starter henting av faktiske Training Effect verdier fra Garmin...")
    asyncio.run(fetch_all_training_effects())
    logger.info("✅ Ferdig!") 