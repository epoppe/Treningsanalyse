#!/usr/bin/env python3
"""
Script for å hente faktiske Training Effect-verdier fra Garmin Connect API
"""

import os
import sys
import asyncio
import logging
from datetime import datetime
from sqlalchemy import or_

# Legg til app-mappen i Python-stien
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.database.session import SessionLocal
from app.database.models.activity import Activity
from app.services.garmin_client import GarminClient
from app.config import settings

# Konfigurer logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def fetch_training_effects_from_garmin():
    """Henter faktiske Training Effect-verdier fra Garmin Connect API"""
    
    db = SessionLocal()
    garmin_client = GarminClient(
        email=settings.GARMIN_EMAIL,
        password=settings.GARMIN_PASSWORD,
        token_dir=settings.TOKEN_DIR
    )
    
    try:
        # Initialiser Garmin-klient
        if not await garmin_client.initialize():
            logger.error("❌ Kunne ikke autentisere med Garmin")
            return
        
        logger.info("✅ Autentisert med Garmin")
        
        # Finn aktiviteter som mangler aerob eller anaerob effekt
        activities_without_effects = db.query(Activity).filter(
            or_(
                Activity.total_training_effect.is_(None),
                Activity.total_anaerobic_training_effect.is_(None)
            )
        ).all()
        
        logger.info(f"Fant {len(activities_without_effects)} aktiviteter som mangler Training Effect verdier")
        
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
    finally:
        db.close()

if __name__ == "__main__":
    logger.info("🚀 Starter henting av faktiske Training Effect verdier fra Garmin...")
    asyncio.run(fetch_training_effects_from_garmin())
    logger.info("✅ Ferdig!") 