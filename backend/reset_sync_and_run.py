#!/usr/bin/env python3
"""
Skript for å tilbakestille SyncState og kjøre historisk synkronisering
"""
import asyncio
import sys
import os
from datetime import datetime, timezone

# Legg til backend-mappen i Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database.session import SessionLocal
from app.database.models.sync_state import SyncState
from app.services.garmin_client import GarminClient
from app.storage import DataStorage
from app.services.sync_service import SyncService

async def reset_sync_state_and_run():
    """Tilbakestill SyncState og kjør historisk synkronisering"""
    db = SessionLocal()
    
    try:
        print("🔄 Tilbakestiller SyncState...")
        
        # Tilbakestill SyncState for aktiviteter
        activities_state = db.query(SyncState).filter_by(key="activities").first()
        if activities_state:
            activities_state.last_synced_date = None
            activities_state.last_synced_at = None
            activities_state.meta = None
            print("✅ SyncState for 'activities' tilbakestilt")
        else:
            activities_state = SyncState(key="activities")
            db.add(activities_state)
            print("✅ SyncState for 'activities' opprettet")
        
        # Tilbakestill SyncState for training effects
        te_state = db.query(SyncState).filter_by(key="training_effect").first()
        if te_state:
            te_state.last_synced_date = None
            te_state.last_synced_at = None
            te_state.meta = None
            print("✅ SyncState for 'training_effect' tilbakestilt")
        else:
            te_state = SyncState(key="training_effect")
            db.add(te_state)
            print("✅ SyncState for 'training_effect' opprettet")
        
        db.commit()
        print("✅ Alle SyncState-endringer lagret i database")
        
        print("\n🚀 Starter historisk synkronisering...")
        
        # Initialiser tjenester
        from app.config import settings
        garmin_client = GarminClient(
            email=settings.GARMIN_EMAIL,
            password=settings.GARMIN_PASSWORD,
            token_dir=settings.TOKEN_DIR
        )
        storage = DataStorage(settings.DATA_DIR)
        sync_service = SyncService(garmin_client, storage, db)
        
        # Definer datoperiode for synkronisering
        start_date = datetime(2010, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2024, 12, 31, tzinfo=timezone.utc)
        
        print(f"📅 Synkroniserer fra {start_date.date()} til {end_date.date()}")
        
        # 1. Synkroniser aktiviteter med FIT-data
        print("\n1️⃣ Synkroniserer aktiviteter og FIT-data...")
        activity_result = await sync_service.sync_activities_with_fit_data(start_date, end_date)
        print(f"✅ Aktiviteter synkronisert: {activity_result}")
        
        # 2. Synkroniser helsedata (HRV fra 2023, som ønsket)
        print("\n2️⃣ Synkroniserer helsedata...")
        await sync_service.sync_health_data(start_date, end_date)
        print("✅ Helsedata synkronisert")
        
        # 3. Synkroniser Training Effect data
        print("\n3️⃣ Synkroniserer Training Effect data...")
        te_result = await sync_service.sync_training_effect_data(start_date, end_date, force_refresh_recent=True)
        print(f"✅ Training Effects synkronisert: {te_result}")
        
        print("\n🎉 Historisk synkronisering fullført!")
        print("📊 Data fra 2010+ er nå tilgjengelig (HRV/Body Battery fra 2023+)")
        
    except Exception as e:
        print(f"❌ Feil under synkronisering: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    print("🔧 Starter tilbakestilling av SyncState og historisk synkronisering...")
    asyncio.run(reset_sync_state_and_run())
