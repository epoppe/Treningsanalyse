#!/usr/bin/env python3
"""
Henter aktiviteter direkte fra Garmin Connect fra 2008 og fremover.
Dette sjekker om det finnes aktiviteter før 2015 i Garmin Connect.
"""

import sys
import os
import asyncio
from datetime import datetime, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

from app.services.garmin_client import GarminClient
from app.config import settings
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def fetch_activities_from_2008():
    """
    Henter aktiviteter fra Garmin Connect fra 2008 og fremover.
    """
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
        
        # Test henting fra 2008
        start_date = datetime(2008, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2015, 1, 1, tzinfo=timezone.utc)
        
        logger.info(f"🔍 Henter aktiviteter fra Garmin Connect: {start_date.date()} til {end_date.date()}")
        
        activities = await garmin_client.get_activities(start_date, end_date)
        
        logger.info(f"✅ Hentet {len(activities)} aktiviteter fra Garmin Connect for perioden 2008-2014")
        
        if activities:
            # Vis første og siste aktivitet
            if len(activities) > 0:
                first_activity = activities[0]
                last_activity = activities[-1]
                
                logger.info(f"📅 Første aktivitet: {first_activity.get('startTimeLocal', 'N/A')}")
                logger.info(f"📅 Siste aktivitet: {last_activity.get('startTimeLocal', 'N/A')}")
                
                # Vis noen eksempler
                logger.info("\n📋 Eksempel-aktiviteter:")
                for i, activity in enumerate(activities[:5], 1):
                    activity_id = activity.get('activityId', 'N/A')
                    activity_name = activity.get('activityName', 'N/A')
                    start_time = activity.get('startTimeLocal', 'N/A')
                    logger.info(f"  {i}. {activity_name} ({start_time}) - ID: {activity_id}")
                
                if len(activities) > 5:
                    logger.info(f"  ... og {len(activities) - 5} flere aktiviteter")
        else:
            logger.warning("⚠️  Ingen aktiviteter funnet i Garmin Connect for perioden 2008-2014")
            logger.info("   Dette kan bety at:")
            logger.info("   - Det ikke finnes aktiviteter i Garmin Connect før 2015")
            logger.info("   - Eller at Garmin API har begrensninger for eldre aktiviteter")
        
        # Test også henting fra 2015 for sammenligning
        logger.info("\n" + "=" * 80)
        start_date_2015 = datetime(2015, 1, 1, tzinfo=timezone.utc)
        end_date_2015 = datetime(2015, 12, 31, tzinfo=timezone.utc)
        
        logger.info(f"🔍 Henter aktiviteter fra Garmin Connect: {start_date_2015.date()} til {end_date_2015.date()}")
        
        activities_2015 = await garmin_client.get_activities(start_date_2015, end_date_2015)
        
        logger.info(f"✅ Hentet {len(activities_2015)} aktiviteter fra Garmin Connect for 2015")
        
        if activities_2015:
            first_activity_2015 = activities_2015[0]
            logger.info(f"📅 Første aktivitet i 2015: {first_activity_2015.get('startTimeLocal', 'N/A')}")
        
    except Exception as e:
        logger.error(f"Feil ved henting av aktiviteter: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    logger.info("🚀 Starter henting av aktiviteter fra 2008...")
    
    asyncio.run(fetch_activities_from_2008())
    
    logger.info("✅ Henting fullført!")

