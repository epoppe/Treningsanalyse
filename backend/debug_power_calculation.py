#!/usr/bin/env python3
"""
Debug-script for å sjekke power-beregning i detalj
"""
import sys
import os

# Legg til backend-mappen i Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database.session import get_db
from app.database.models.activity import Activity
from app.storage import DataStorage
from app.services.power_service import PowerService

def debug_power_calculation():
    """Debug power-beregning for aktivitet 19861351641"""
    
    print("🔍 DEBUG POWER-BEREGNING FOR AKTIVITET 19861351641")
    print("=" * 60)
    
    db = next(get_db())
    storage = DataStorage()
    power_service = PowerService(storage)
    
    try:
        # Hent aktivitet
        activity = db.query(Activity).filter(Activity.activity_id == "19861351641").first()
        if not activity:
            print("❌ Kunne ikke finne aktivitet")
            return
        
        print(f"Aktivitet: {activity.activity_name}")
        print(f"Gjennomsnittlig hastighet: {activity.average_speed} m/s")
        print(f"Gjennomsnittlig hastighet: {activity.average_speed * 3.6} km/h")
        print()
        
        # Hent FIT-data
        details_df = storage.get_activity_details("19861351641")
        if details_df is None or details_df.empty:
            print("❌ Ingen FIT-data tilgjengelig")
            return
        
        print(f"FIT-data kolonner: {list(details_df.columns)}")
        print(f"Antall datapunkter: {len(details_df)}")
        print()
        
        # Sjekk hastighetsdata
        if 'speed' in details_df.columns:
            speed_data = details_df['speed'].dropna()
            print(f"Hastighetsdata:")
            print(f"  Min: {speed_data.min():.2f} m/s ({speed_data.min() * 3.6:.2f} km/h)")
            print(f"  Max: {speed_data.max():.2f} m/s ({speed_data.max() * 3.6:.2f} km/h)")
            print(f"  Gjennomsnitt: {speed_data.mean():.2f} m/s ({speed_data.mean() * 3.6:.2f} km/h)")
            print()
        
        # Test power-beregning for noen datapunkter
        valid_data = details_df.dropna(subset=['speed', 'timestamp'])
        valid_data = valid_data[(valid_data['speed'] > 0)]
        
        if len(valid_data) > 0:
            print("Test power-beregning for første 5 datapunkter:")
            prev_speed = 0.0
            
            for i, (idx, row) in enumerate(valid_data.head(5).iterrows()):
                speed = row['speed']
                grade = row.get('grade', 0.0) if pd.notna(row.get('grade')) else 0.0
                vo = row.get('vertical_oscillation', 0.0) if pd.notna(row.get('vertical_oscillation')) else 0.0
                gct = row.get('stance_time', 0.0) if pd.notna(row.get('stance_time')) else 0.0
                
                power = power_service.running_power(70.0, speed, prev_speed, grade, vo, gct)
                
                print(f"  Punkt {i+1}:")
                print(f"    Hastighet: {speed:.2f} m/s ({speed * 3.6:.2f} km/h)")
                print(f"    Stigning: {grade:.2f}%")
                print(f"    Vertikal oscillasjon: {vo:.2f} cm")
                print(f"    Ground contact time: {gct:.2f} ms")
                print(f"    Power: {power:.1f} W")
                print()
                
                prev_speed = speed
        
        # Beregn power på nytt
        print("Beregner power på nytt...")
        power_result = power_service.calculate_activity_power(19861351641, db)
        
        if power_result:
            print(f"Resultat:")
            print(f"  Gjennomsnittlig power: {power_result['average_power_watts']} W")
            print(f"  Maksimal power: {power_result['max_power_watts']} W")
            print(f"  Minimal power: {power_result['min_power_watts']} W")
            print(f"  Antall datapunkter: {power_result['data_points']}")
        else:
            print("❌ Kunne ikke beregne power")
            
    except Exception as e:
        print(f"❌ Feil: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    debug_power_calculation()