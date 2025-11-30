#!/usr/bin/env python3
"""
Starter full synkronisering av aktiviteter fra 2008-01-01 og fremover.
Dette vil hente alle aktiviteter fra Garmin Connect og beregne TSS for dem.
"""

import sys
import os
import asyncio
from datetime import datetime, date, timezone
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


async def sync_from_2008():
    """
    Starter full synkronisering fra 2008-01-01.
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
        
        # Initialiser SyncService
        sync_service = SyncService(garmin_client, storage, db)
        
        # Sett datoer
        start_date = datetime(2008, 1, 1, tzinfo=timezone.utc)
        end_date = datetime.now(timezone.utc)
        
        logger.info(f"🚀 Starter full synkronisering fra {start_date.date()} til {end_date.date()}")
        logger.info("📝 Dette kan ta lang tid avhengig av antall aktiviteter...")
        logger.info("   Aktiviteter og FIT-data vil hentes fra 2008")
        logger.info("   Helsedata (HRV, Body Battery, Training Effect) vil hentes fra 2020")
        
        # 1. Synkroniser aktiviteter med FIT-data
        logger.info("=" * 80)
        logger.info("Steg 1/4: Synkroniserer aktiviteter og FIT-data...")
        activity_result = await sync_service.sync_activities_with_fit_data(
            start_date,
            end_date,
            force_refresh_recent=True,
            fit_data_limit=150,
            ignore_sync_state=True,  # Ignorer sync state for å hente alt fra 2008
            fit_download_mode="chunked"
        )
        
        logger.info(f"✅ Aktivitetssynkronisering fullført: {activity_result}")
        
        # 2. Beregn TSS for alle nye aktiviteter
        logger.info("=" * 80)
        logger.info("Steg 2/4: Beregner TSS for alle aktiviteter...")
        
        from app.services.training_stress_service import TrainingStressService
        tss_service = TrainingStressService(db)
        
        # Hent alle aktiviteter fra 2008 som mangler TSS
        activities_without_tss = db.query(Activity).filter(
            Activity.start_time >= start_date,
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
        
        # 3. Synkroniser helsedata (kun fra 2020)
        health_start_date = datetime(2020, 1, 1, tzinfo=timezone.utc)
        logger.info("=" * 80)
        logger.info(f"Steg 3/4: Synkroniserer helsedata fra {health_start_date.date()}...")
        await sync_service.sync_health_data(health_start_date, end_date)
        logger.info("✅ Helsedata synkronisert")
        
        # 4. Synkroniser Training Effect data (kun fra 2020)
        logger.info("=" * 80)
        logger.info(f"Steg 4/4: Synkroniserer Training Effect data fra {health_start_date.date()}...")
        await sync_service.sync_training_effect_data(health_start_date, end_date, force_refresh_recent=True)
        logger.info("✅ Training Effect data synkronisert")
        
        logger.info("=" * 80)
        logger.info("✅ Full synkronisering fullført!")
        
        # Vis statistikk
        total_activities = db.query(Activity).filter(
            Activity.start_time >= start_date
        ).count()
        
        activities_with_tss = db.query(Activity).filter(
            Activity.start_time >= start_date,
            Activity.training_stress_score.isnot(None),
            Activity.training_stress_score > 0
        ).count()
        
        logger.info(f"📊 Totalt {total_activities} aktiviteter fra 2008")
        logger.info(f"📊 {activities_with_tss} aktiviteter har TSS-data")
        
    except Exception as e:
        logger.error(f"Feil ved synkronisering: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logger.info("🚀 Starter full synkronisering fra 2008-01-01...")
    logger.info("📝 Dette kan ta lang tid avhengig av antall aktiviteter...")
    
    asyncio.run(sync_from_2008())
    
    logger.info("✅ Synkronisering fullført!")

