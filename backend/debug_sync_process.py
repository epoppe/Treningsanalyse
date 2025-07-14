#!/usr/bin/env python3
"""
Script for å debugge synkroniseringsprosessen og finne hvor den feiler
"""

import os
import sys
import asyncio
from datetime import datetime, timedelta, timezone

# Legg til app-mappen i Python-stien
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.services.garmin_client import GarminClient
from app.services.sync_service import SyncService
from app.storage import DataStorage
from app.database.session import SessionLocal
from app.config import settings

async def debug_sync_process():
    """Debug hele synkroniseringsprosessen"""
    print("🔍 Debugger synkroniseringsprosessen...")
    
    # Opprett komponenter
    garmin_client = GarminClient(
        email=settings.GARMIN_EMAIL,
        password=settings.GARMIN_PASSWORD,
        token_dir=settings.TOKEN_DIR
    )
    
    storage = DataStorage(data_dir=settings.DATA_DIR)
    db_session = SessionLocal()
    
    try:
        # 1. Test Garmin-autentisering
        print("\n1️⃣ Tester Garmin-autentisering...")
        if not await garmin_client.initialize():
            print("❌ Garmin-autentisering feilet")
            return
        print("✅ Garmin-klient autentisert")
        
        # 2. Hent aktiviteter fra Garmin API
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=2)
        
        print(f"\n2️⃣ Henter aktiviteter fra Garmin: {start_date.date()} til {end_date.date()}")
        activities_raw = await garmin_client.get_activities(start_date, end_date)
        print(f"📊 Garmin returnerte: {len(activities_raw)} aktiviteter")
        
        if not activities_raw:
            print("❌ Ingen aktiviteter fra Garmin")
            return
            
        # 3. Sjekk eksisterende aktiviteter i database
        print("\n3️⃣ Sjekker eksisterende aktiviteter i database...")
        existing_ids = storage.get_existing_activity_ids(db_session)
        print(f"📊 Fant {len(existing_ids)} eksisterende aktiviteter i database")
        
        # 4. Analyser hver aktivitet
        print("\n4️⃣ Analyserer hver aktivitet fra Garmin:")
        recent_cutoff = datetime.now(timezone.utc) - timedelta(days=2)
        force_refresh_recent = True
        
        for i, act_data in enumerate(activities_raw):
            activity_id = str(act_data.get('activityId'))
            activity_name = act_data.get('activityName', 'Ukjent')
            start_time_gmt = act_data.get('startTimeGMT', 'Ukjent')
            
            print(f"\n   Aktivitet {i+1}: {activity_id} - {activity_name}")
            print(f"   Start tid: {start_time_gmt}")
            
            # Sjekk om aktiviteten finnes i database
            is_in_db = activity_id in existing_ids
            print(f"   Finnes i database: {'✅ Ja' if is_in_db else '❌ Nei'}")
            
            # Sjekk om aktiviteten er nylig
            try:
                activity_start_time = datetime.fromisoformat(act_data['startTimeGMT'])
                if activity_start_time.tzinfo is None:
                    activity_start_time = activity_start_time.replace(tzinfo=timezone.utc)
                is_recent = activity_start_time >= recent_cutoff
                print(f"   Er nylig (siste 2 dager): {'✅ Ja' if is_recent else '❌ Nei'}")
                
                # Beregn om aktiviteten skal hoppes over
                should_skip = (activity_id in existing_ids and 
                              not (force_refresh_recent and is_recent))
                print(f"   Skal hoppes over: {'✅ Ja' if should_skip else '❌ Nei'}")
                print(f"   Force refresh recent aktiv: {'✅ Ja' if force_refresh_recent else '❌ Nei'}")
                
                if should_skip:
                    print("   🔄 HOPPES OVER: Aktivitet finnes og er ikke nylig nok")
                else:
                    print("   ✅ SKAL SYNKRONISERES: Ny aktivitet eller nylig oppdatering")
                    
            except Exception as e:
                print(f"   ❌ Feil ved parsing av start tid: {e}")
        
        # 5. Test faktisk synkronisering
        print(f"\n5️⃣ Tester faktisk synkronisering...")
        sync_service = SyncService(garmin_client, storage, db_session)
        
        try:
            result = await sync_service.sync_activities(start_date, end_date, force_refresh_recent)
            print(f"📊 Synkroniseringsresultat: {result}")
            
            if result.get('total_fetched', 0) > 0:
                print(f"✅ Lagt til {result['total_fetched']} nye aktiviteter")
            else:
                print("❌ Ingen nye aktiviteter lagt til")
                print(f"Status: {result.get('status', 'Ukjent')}")
                
        except Exception as e:
            print(f"❌ Feil under synkronisering: {e}")
            import traceback
            traceback.print_exc()
    
    finally:
        db_session.close()

if __name__ == "__main__":
    asyncio.run(debug_sync_process()) 