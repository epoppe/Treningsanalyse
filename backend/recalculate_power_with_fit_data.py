#!/usr/bin/env python3
"""
Script for å beregne power på nytt kun for aktiviteter som har FIT-data
"""
import sys
import os
from datetime import datetime

# Legg til backend-mappen i Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database.session import get_db
from app.database.models.activity import Activity, ActivityType
from app.storage import DataStorage
from app.services.power_service import PowerService
from sqlalchemy import and_

def recalculate_power_with_fit_data():
    """Beregn power på nytt kun for aktiviteter som har FIT-data"""
    
    print("🔋 BEREGNER POWER PÅ NYTT FOR AKTIVITETER MED FIT-DATA")
    print("=" * 60)
    
    db = next(get_db())
    storage = DataStorage()
    power_service = PowerService(storage)
    
    try:
        # Hent ID for løpingstypen
        running_type = db.query(ActivityType).filter(ActivityType.type_key == 'running').first()
        if not running_type:
            print("❌ Kunne ikke finne løpingstype")
            return
        
        # Hent alle løpeaktiviteter fra 2020 og fremover
        activities = db.query(Activity).filter(
            and_(
                Activity.activity_type_id == running_type.id,
                Activity.start_time >= datetime(2020, 1, 1)
            )
        ).order_by(Activity.start_time.desc()).all()
        
        print(f"📊 Fant {len(activities)} løpeaktiviteter fra 2020+")
        print()
        
        success_count = 0
        fit_data_count = 0
        total_count = 0
        
        for activity in activities:
            total_count += 1
            activity_id = int(activity.activity_id)
            
            # Sjekk om FIT-data er tilgjengelig
            details_df = storage.get_activity_details(activity_id)
            if details_df is None or details_df.empty:
                continue
            
            fit_data_count += 1
            
            # Sjekk at vi har nødvendige kolonner
            if 'speed' not in details_df.columns or 'timestamp' not in details_df.columns:
                continue
            
            # Filtrer ut rader med gyldig speed og timestamp data
            valid_data = details_df.dropna(subset=['speed', 'timestamp'])
            valid_data = valid_data[(valid_data['speed'] > 0)]
            
            if len(valid_data) < 10:
                continue
            
            print(f"🔋 Beregner power for aktivitet {activity_id} ({activity.activity_name})")
            
            try:
                # Beregn power på nytt
                power_result = power_service.calculate_activity_power(activity_id, db)
                
                if power_result:
                    avg_power = power_result['average_power_watts']
                    max_power = power_result['max_power_watts']
                    
                    print(f"   ✅ Power: {avg_power:.1f}W (max: {max_power:.1f}W)")
                    success_count += 1
                else:
                    print(f"   ❌ Kunne ikke beregne power")
                    
            except Exception as e:
                print(f"   ❌ Feil: {e}")
            
            # Vis fremdrift hver 50. aktivitet
            if total_count % 50 == 0:
                print(f"📈 Fremdrift: {total_count}/{len(activities)} aktiviteter behandlet")
        
        print()
        print("=" * 60)
        print("📊 SAMMENDRAG")
        print(f"Totalt aktiviteter: {len(activities)}")
        print(f"Aktiviteter med FIT-data: {fit_data_count}")
        print(f"Power beregnet: {success_count}")
        print(f"Suksessrate: {(success_count/fit_data_count*100):.1f}%" if fit_data_count > 0 else "N/A")
        
    except Exception as e:
        print(f"❌ Feil: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    recalculate_power_with_fit_data()