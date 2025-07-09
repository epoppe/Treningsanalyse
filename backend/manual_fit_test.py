import asyncio
from app.services.garmin_client import GarminClient
from app.storage import DataStorage
from app.services.sync_service import SyncService
from app.database.session import SessionLocal
from app.config import settings

async def manual_fit_test():
    # Test en spesifikk aktivitet som vi vet mangler FIT-data
    activity_id = 9990507603  # Fra listen over aktiviteter som mangler data
    
    try:
        garmin_client = GarminClient(
            email=settings.GARMIN_EMAIL,
            password=settings.GARMIN_PASSWORD,
            token_dir=settings.TOKEN_DIR
        )
        storage = DataStorage()
        db = SessionLocal()
        sync_service = SyncService(garmin_client, storage, db)
        
        if not await garmin_client.initialize():
            print("Kunne ikke initialisere Garmin-klient")
            return
        
        print(f"Tester full FIT-data nedlasting for aktivitet {activity_id}...")
        
        # Test full nedlasting og lagring
        success = await sync_service._download_and_store_fit_file(activity_id)
        
        if success:
            print(f"✓ FIT-data nedlasting vellykket for aktivitet {activity_id}")
            
            # Sjekk at data ble lagret
            from app.database.models.activity import Activity
            activity = db.query(Activity).filter_by(id=activity_id).first()
            if activity and activity.details:
                print(f"✓ Database oppdatert med details ({len(str(activity.details))} tegn)")
            else:
                print("✗ Database ikke oppdatert")
                
        else:
            print(f"✗ FIT-data nedlasting feilet for aktivitet {activity_id}")
    
    except Exception as e:
        print(f"Feil under test: {e}")
        
    finally:
        if 'db' in locals():
            db.close()

if __name__ == "__main__":
    asyncio.run(manual_fit_test()) 