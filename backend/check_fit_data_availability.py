#!/usr/bin/env python3
"""
Script for å sjekke hvilke aktiviteter som har FIT-data tilgjengelig
"""
import sys
import os
from datetime import datetime, timedelta

# Legg til backend-mappen i Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database.session import get_db
from app.database.models.activity import Activity, ActivityType
from app.storage import DataStorage
from app.config import settings
from sqlalchemy import and_

def check_fit_data_availability():
    """Sjekk hvilke aktiviteter som har FIT-data tilgjengelig"""
    
    print("🔍 SJEKKER FIT-DATA TILGJENGELIGHET")
    print("=" * 60)
    
    db = next(get_db())
    storage = DataStorage(settings.DATA_DIR)
    
    try:
        # Hent ID for løpingstypen
        running_type = db.query(ActivityType).filter(ActivityType.type_key == 'running').first()
        if not running_type:
            print("❌ Aktivitetstypen 'running' ble ikke funnet")
            return
        
        # Hent nyere løpeaktiviteter (fra 2020 og fremover)
        start_date = datetime(2020, 1, 1)
        
        activities = db.query(Activity).filter(
            and_(
                Activity.activity_type_id == running_type.id,
                Activity.start_time >= start_date
            )
        ).order_by(Activity.start_time.desc()).limit(50).all()  # Sjekk første 50
        
        print(f"📊 Sjekker FIT-data for {len(activities)} løpeaktiviteter fra 2020+")
        
        activities_with_fit = 0
        activities_without_fit = 0
        
        for i, activity in enumerate(activities, 1):
            print(f"\n🔍 Aktivitet {i}: {activity.activity_id}")
            print(f"   Dato: {activity.start_time}")
            print(f"   Distanse: {activity.distance/1000:.2f} km")
            
            # Sjekk om FIT-data finnes
            details_df = storage.get_activity_details(int(activity.activity_id))
            
            if details_df is not None and not details_df.empty:
                print(f"   ✅ FIT-data tilgjengelig: {len(details_df)} datapunkter")
                activities_with_fit += 1
                
                # Sjekk nødvendige kolonner for power-beregning
                required_columns = ['speed', 'timestamp']
                missing_columns = [col for col in required_columns if col not in details_df.columns]
                
                if missing_columns:
                    print(f"   ⚠️  Mangler kolonner: {missing_columns}")
                else:
                    print(f"   ✅ Alle nødvendige kolonner tilgjengelig")
                    
            else:
                print(f"   ❌ Ingen FIT-data tilgjengelig")
                activities_without_fit += 1
        
        print(f"\n📈 FIT-DATA OVERSIKT")
        print("=" * 60)
        print(f"✅ Med FIT-data: {activities_with_fit}")
        print(f"❌ Uten FIT-data: {activities_without_fit}")
        print(f"📊 Total sjekket: {len(activities)}")
        
        if activities_with_fit > 0:
            print(f"\n🎉 {activities_with_fit} aktiviteter har FIT-data og kan beregne power!")
        
    except Exception as e:
        print(f"❌ Feil: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_fit_data_availability()