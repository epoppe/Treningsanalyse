import asyncio
from app.services.garmin_client import GarminClient
from app.services.sync_service import SyncService
from app.config import settings

async def debug_fit_parsing():
    activity_id = 9990507603
    
    garmin_client = GarminClient(
        email=settings.GARMIN_EMAIL,
        password=settings.GARMIN_PASSWORD,
        token_dir=settings.TOKEN_DIR
    )
    sync_service = SyncService(garmin_client, None, None)
    
    if not await garmin_client.initialize():
        print("Kunne ikke initialisere Garmin-klient")
        return
    
    print(f"=== DEBUG FIT-PARSING FOR AKTIVITET {activity_id} ===")
    
    # Hent FIT-data fra Garmin
    fit_data = await garmin_client.get_activity_details(activity_id)
    if not fit_data:
        print("❌ Ingen FIT-data fra Garmin")
        return
    
    print(f"✓ Hentet FIT-data ({len(fit_data)} bytes)")
    
    # Parse FIT-data
    details_json = sync_service._parse_fit_data(fit_data)
    if not details_json or 'records' not in details_json:
        print("❌ FIT-parsing feilet")
        return
    
    records = details_json['records']
    print(f"✓ Parset {len(records)} FIT-records")
    
    # Undersøk de første recordsene
    print(f"\n=== FØRSTE 3 RECORDS ===")
    for i, record in enumerate(records[:3]):
        print(f"\nRecord {i+1}:")
        for key, value in record.items():
            print(f"  {key}: {value} (type: {type(value)})")
    
    # Sjekk speed-related felter
    print(f"\n=== SPEED-ANALYSE ===")
    speed_fields = []
    sample_record = records[0] if records else {}
    
    for key in sample_record.keys():
        if 'speed' in key.lower() or 'velocity' in key.lower() or 'pace' in key.lower():
            speed_fields.append(key)
    
    print(f"Speed-relaterte felter funnet: {speed_fields}")
    
    # Analyser speed-verdier
    if 'speed' in sample_record:
        speed_values = [r.get('speed') for r in records[:10]]
        print(f"Første 10 speed-verdier: {speed_values}")
    
    # Sjekk alle felter i første record
    print(f"\n=== ALLE FELTER I FØRSTE RECORD ===")
    if records:
        for key, value in records[0].items():
            print(f"{key}: {value}")

if __name__ == "__main__":
    asyncio.run(debug_fit_parsing()) 