#!/usr/bin/env python3
"""
Script for å beregne power for nyere løpeaktiviteter (fra 2020 og fremover)
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
from app.services.power_service import PowerService
from sqlalchemy import and_

def calculate_power_recent_activities():
    """Beregn power for nyere løpeaktiviteter som ikke har power-verdier"""
    
    print("🔋 STARTER POWER-BEREGNING FOR NYERE LØPEAKTIVITETER")
    print("=" * 60)
    
    db = next(get_db())
    storage = DataStorage(settings.DATA_DIR)
    power_service = PowerService(storage)
    
    try:
        # Hent ID for løpingstypen
        running_type = db.query(ActivityType).filter(ActivityType.type_key == 'running').first()
        if not running_type:
            print("❌ Aktivitetstypen 'running' ble ikke funnet")
            return
        
        # Fokus på aktiviteter fra 2020 og fremover
        start_date = datetime(2020, 1, 1)
        
        # Hent nyere løpeaktiviteter som ikke har power-verdier
        activities_without_power = db.query(Activity).filter(
            and_(
                Activity.activity_type_id == running_type.id,
                Activity.start_time >= start_date,
                (Activity.average_power == None) | (Activity.max_power == None)
            )
        ).order_by(Activity.start_time.desc()).all()
        
        total_activities = len(activities_without_power)
        print(f"📊 Fant {total_activities} løpeaktiviteter fra 2020+ uten power-verdier")
        
        if total_activities == 0:
            print("✅ Alle nyere løpeaktiviteter har allerede power-verdier!")
            return
        
        # Beregn power for hver aktivitet
        successful_count = 0
        failed_count = 0
        
        for i, activity in enumerate(activities_without_power, 1):
            print(f"\n🔋 Prosesserer aktivitet {i}/{total_activities}: {activity.activity_id}")
            print(f"   Dato: {activity.start_time}")
            print(f"   Distanse: {activity.distance/1000:.2f} km")
            
            try:
                # Beregn power
                power_result = power_service.calculate_activity_power(int(activity.activity_id), db)
                
                if power_result:
                    print(f"   ✅ Power beregnet: {power_result['average_power_watts']:.1f}W (avg)")
                    successful_count += 1
                else:
                    print(f"   ❌ Kunne ikke beregne power")
                    failed_count += 1
                    
            except Exception as e:
                print(f"   ❌ Feil ved power-beregning: {e}")
                failed_count += 1
        
        print(f"\n📈 POWER-BEREGNING FULLFØRT")
        print("=" * 60)
        print(f"✅ Vellykket: {successful_count}")
        print(f"❌ Feilet: {failed_count}")
        print(f"📊 Total: {total_activities}")
        
        if successful_count > 0:
            print(f"\n🎉 {successful_count} aktiviteter har nå power-verdier!")
        
    except Exception as e:
        print(f"❌ Feil: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    calculate_power_recent_activities()