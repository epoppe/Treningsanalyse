#!/usr/bin/env python3
"""
Script for å laste ned FIT-data for aktiviteter fra 21. og 23. juli og beregne negative split og decoupling
"""
import sys
import os
from datetime import datetime, timedelta

# Legg til backend-mappen i Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database.session import get_db
from app.database.models.activity import Activity, ActivityType
from app.services.sync_service import SyncService
from app.services.garmin_client import GarminClient
from app.storage import DataStorage
from app.services.analysis_service import AnalysisService
from app.config import settings
import logging
import asyncio

# Konfigurer logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def download_fit_data_and_calculate():
    """Last ned FIT-data og beregn negative split og decoupling"""
    
    # Aktivitetene som mangler FIT-data
    activity_ids = [19799492161, 19820769287]
    
    print("🚀 STARTER NEDLASTING AV FIT-DATA FOR JULI-AKTIVITETER")
    print("=" * 60)
    print("Aktiviter som skal prosesseres:")
    for activity_id in activity_ids:
        print(f"   - {activity_id}")
    print("=" * 60)
    
    # Initialiser services
    storage = DataStorage(settings.DATA_DIR)
    garmin_client = GarminClient(
        email=settings.GARMIN_EMAIL,
        password=settings.GARMIN_PASSWORD,
        token_dir=settings.TOKEN_DIR
    )
    
    # Initialiser Garmin-klienten
    success = await garmin_client.initialize()
    if not success:
        print("❌ Kunne ikke initialisere Garmin-klienten")
        return
    
    sync_service = SyncService(garmin_client, storage, None)
    analysis_service = AnalysisService(storage)
    db = next(get_db())
    
    try:
        for i, activity_id in enumerate(activity_ids, 1):
            print(f"\n📥 Prosesserer aktivitet {i}/{len(activity_ids)}: {activity_id}")
            
            # Hent aktivitet fra database
            activity = db.query(Activity).filter(Activity.activity_id == str(activity_id)).first()
            if not activity:
                print(f"   ❌ Aktivitet {activity_id} ikke funnet i database")
                continue
            
            print(f"   📊 Aktivitet: {activity.activity_name}")
            print(f"   📅 Dato: {activity.start_time}")
            print(f"   🏃‍♂️ Distanse: {activity.distance/1000:.2f} km")
            
            # Sjekk om FIT-data allerede finnes
            existing_fit = storage.get_activity_details(activity_id)
            if existing_fit is not None and len(existing_fit) > 0:
                print(f"   ✅ FIT-data finnes allerede ({len(existing_fit)} datapunkter)")
            else:
                print(f"   ⬇️  Laster ned FIT-data...")
                
                try:
                    # Last ned FIT-data
                    await sync_service._download_and_store_fit_file(activity_id)
                    print(f"   ✅ FIT-data lastet ned og lagret")
                        
                except Exception as e:
                    print(f"   ❌ Feil ved nedlasting av FIT-data: {e}")
                    continue
            
            # Beregn negative split
            print(f"   🧮 Beregner negative split...")
            try:
                negative_split_result = analysis_service.calculate_negative_split(activity_id, db)
                if negative_split_result:
                    print(f"   ✅ Negative split: {negative_split_result['negative_split_percent']:.2f}%")
                else:
                    print(f"   ❌ Kunne ikke beregne negative split")
            except Exception as e:
                print(f"   ❌ Feil ved beregning av negative split: {e}")
            
            # Beregn decoupling
            print(f"   🧮 Beregner decoupling...")
            try:
                decoupling_result = analysis_service.calculate_decoupling(activity_id, db)
                if decoupling_result:
                    print(f"   ✅ Decoupling: {decoupling_result['decoupling_percent']:.2f}%")
                else:
                    print(f"   ❌ Kunne ikke beregne decoupling")
            except Exception as e:
                print(f"   ❌ Feil ved beregning av decoupling: {e}")
            
            print(f"   ✅ Aktivitet {activity_id} fullført")
            
    except Exception as e:
        print(f"❌ Feil: {e}")
        logger.error(f"Feil i hovedfunksjon: {e}")
    finally:
        db.close()
    
    print("\n🎉 NEDLASTING OG BEREGNING FULLFØRT!")
    print("   FIT-data er lastet ned og negative split/decoupling er beregnet")

if __name__ == "__main__":
    asyncio.run(download_fit_data_and_calculate()) 