import asyncio
from app.services.garmin_client import GarminClient
from app.services.sync_service import SyncService
from app.config import settings

async def debug_speed_extraction():
    activity_id = 9975737879
    
    garmin_client = GarminClient(
        email=settings.GARMIN_EMAIL,
        password=settings.GARMIN_PASSWORD,
        token_dir=settings.TOKEN_DIR
    )
    sync_service = SyncService(garmin_client, None, None)
    
    if not await garmin_client.initialize():
        print("Kunne ikke initialisere Garmin-klient")
        return
    
    print(f"=== DEBUG SPEED-EXTRAKSJON FOR AKTIVITET {activity_id} ===")
    
    # Hent FIT-data fra Garmin
    fit_data = await garmin_client.get_activity_details(activity_id)
    if not fit_data:
        print("❌ Ingen FIT-data fra Garmin")
        return
    
    # Parse FIT-data
    details_json = sync_service._parse_fit_data(fit_data)
    if not details_json or 'records' not in details_json:
        print("❌ FIT-parsing feilet")
        return
    
    records = details_json['records']
    print(f"✓ Parset {len(records)} FIT-records")
    
    # Test de første 5 recordsene
    print(f"\n=== TESTING SPEED-EXTRAKSJON ===")
    for i, record in enumerate(records[:5]):
        enhanced_speed = record.get('enhanced_speed')
        speed = record.get('speed')
        
        print(f"\nRecord {i+1}:")
        print(f"  enhanced_speed: {enhanced_speed} (type: {type(enhanced_speed)})")
        print(f"  speed: {speed} (type: {type(speed)})")
        
        # Test extraction logic
        speed_value = enhanced_speed or speed
        print(f"  speed_value (after or): {speed_value} (type: {type(speed_value)})")
        
        # Test _extract_numeric_value
        extracted = sync_service._extract_numeric_value(speed_value)
        print(f"  extracted value: {extracted} (type: {type(extracted)})")
        
        # Test full record creation
        parquet_record = {
            'speed': sync_service._extract_numeric_value(record.get('enhanced_speed') or record.get('speed')),
            'heart_rate': sync_service._extract_numeric_value(record.get('heart_rate')),
            'cadence': sync_service._extract_numeric_value(record.get('cadence'))
        }
        print(f"  final parquet_record: {parquet_record}")

if __name__ == "__main__":
    asyncio.run(debug_speed_extraction()) 