#!/usr/bin/env python3
"""
Synkroniserer aktiviteter fra 2008 til 2015 i mindre chunks for å unngå API-begrensninger.
Garmin API returnerer maksimalt 99 aktiviteter per forespørsel.
"""

import sys
import os
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

from app.database.session import SessionLocal
from app.services.garmin_client import GarminClient
from app.storage import DataStorage
from app.services.sync_service import SyncService
from app.config import settings
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def sync_activities_2008_2015():
    """
    Synkroniserer aktiviteter fra 2008 til 2015 i månedlige chunks.
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
        
        # Initialiser DataStorage og SyncService
        storage = DataStorage(settings.DATA_DIR)
        sync_service = SyncService(garmin_client, storage, db)
        
        # Start fra 2008-01-01 til 2015-02-02 (når eksisterende aktiviteter starter)
        start_date = datetime(2008, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2015, 2, 2, tzinfo=timezone.utc)
        
        logger.info(f"🚀 Starter synkronisering fra {start_date.date()} til {end_date.date()}")
        logger.info("📝 Henter aktiviteter i månedlige chunks for å unngå API-begrensninger...")
        
        # Hent aktiviteter i månedlige chunks
        current_start = start_date
        total_synced = 0
        
        while current_start < end_date:
            # Beregn sluttdato for denne chunken (1 måned)
            current_end = min(
                current_start + timedelta(days=31),
                end_date
            )
            
            logger.info("=" * 80)
            logger.info(f"📅 Synkroniserer periode: {current_start.date()} til {current_end.date()}")
            
            try:
                # Synkroniser aktiviteter for denne perioden
                result = await sync_service.sync_activities_with_fit_data(
                    current_start,
                    current_end,
                    force_refresh_recent=False,
                    fit_data_limit=50,  # Lavere limit for eldre aktiviteter
                    ignore_sync_state=True,  # Ignorer sync state for å hente alt
                    fit_download_mode="chunked"
                )
                
                synced_count = result.get('total_fetched', 0)
                total_synced += synced_count
                
                logger.info(f"✅ Synkronisert {synced_count} aktiviteter for perioden {current_start.date()} til {current_end.date()}")
                
            except Exception as e:
                logger.error(f"❌ Feil ved synkronisering av periode {current_start.date()} til {current_end.date()}: {e}")
                # Fortsett med neste periode
                pass
            
            # Gå til neste måned
            current_start = current_end
        
        logger.info("=" * 80)
        logger.info(f"✅ Synkronisering fullført! Totalt {total_synced} nye aktiviteter synkronisert")
        
        # Beregn TSS for alle nye aktiviteter
        logger.info("=" * 80)
        logger.info("📊 Beregner TSS for alle nye aktiviteter...")
        
        from app.services.training_stress_service import TrainingStressService
        from app.database.models.activity import Activity
        
        tss_service = TrainingStressService(db)
        
        # Hent alle aktiviteter fra 2008 til 2015 som mangler TSS
        activities_without_tss = db.query(Activity).filter(
            Activity.start_time >= datetime(2008, 1, 1, tzinfo=timezone.utc),
            Activity.start_time < datetime(2015, 2, 2, tzinfo=timezone.utc),
            Activity.training_stress_score.is_(None)
        ).all()
        
        logger.info(f"Fant {len(activities_without_tss)} aktiviteter som mangler TSS")
        
        tss_calculated = 0
        for i, activity in enumerate(activities_without_tss, 1):
            try:
                tss = tss_service.calculate_tss_for_activity(activity)
                if tss and tss > 0:
                    activity.training_stress_score = tss
                    tss_calculated += 1
                    
                    if i % 50 == 0:
                        db.commit()
                        logger.info(f"  ✅ Committet {i} aktiviteter så langt...")
            except Exception as e:
                logger.warning(f"Kunne ikke beregne TSS for aktivitet {activity.activity_id}: {e}")
        
        db.commit()
        logger.info(f"✅ Beregnet TSS for {tss_calculated} aktiviteter")
        
        # Vis statistikk
        total_activities = db.query(Activity).filter(
            Activity.start_time >= datetime(2008, 1, 1, tzinfo=timezone.utc)
        ).count()
        
        activities_with_tss = db.query(Activity).filter(
            Activity.start_time >= datetime(2008, 1, 1, tzinfo=timezone.utc),
            Activity.training_stress_score.isnot(None),
            Activity.training_stress_score > 0
        ).count()
        
        earliest = db.query(Activity).order_by(Activity.start_time.asc()).first()
        
        logger.info("=" * 80)
        logger.info(f"📊 Statistikk:")
        logger.info(f"   Tidligste aktivitet: {earliest.start_time.date() if earliest else None}")
        logger.info(f"   Totalt aktiviteter fra 2008: {total_activities}")
        logger.info(f"   Aktiviteter med TSS: {activities_with_tss}")
        
    except Exception as e:
        logger.error(f"Feil ved synkronisering: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logger.info("🚀 Starter synkronisering av aktiviteter fra 2008 til 2015...")
    logger.info("📝 Dette kan ta lang tid avhengig av antall aktiviteter...")
    
    asyncio.run(sync_activities_2008_2015())
    
    logger.info("✅ Synkronisering fullført!")

