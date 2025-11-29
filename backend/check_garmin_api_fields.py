#!/usr/bin/env python3
"""
Skript for å sjekke hvilke felter Garmin API returnerer for aktiviteter
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.garmin_client import GarminClient
from app.config import settings
import asyncio
from datetime import datetime, timedelta, timezone

async def check_api_fields():
    garmin_client = GarminClient(
        email=settings.GARMIN_EMAIL,
        password=settings.GARMIN_PASSWORD,
        token_dir=settings.GARMIN_TOKEN_DIR
    )
    
    if not await garmin_client.initialize():
        print("Kunne ikke initialisere Garmin-klient")
        return
    
    # Hent de siste aktivitetene
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=7)
    
    activities = await garmin_client.get_activities(start_date, end_date)
    
    if activities and len(activities) > 0:
        print(f"Fant {len(activities)} aktiviteter")
        print("\nFelt i første aktivitet:")
        first_activity = activities[0]
        for key in sorted(first_activity.keys()):
            value = first_activity[key]
            if 'elevation' in key.lower() or 'ascent' in key.lower() or 'descent' in key.lower() or 'gain' in key.lower():
                print(f"  {key}: {value} (TYPE: {type(value).__name__})")
        
        print("\nAlle felt i første aktivitet:")
        for key in sorted(first_activity.keys()):
            value = first_activity[key]
            if value is not None:
                print(f"  {key}: {value}")

if __name__ == "__main__":
    asyncio.run(check_api_fields())

