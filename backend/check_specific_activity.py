#!/usr/bin/env python3
"""
Script for å sjekke power-verdi for en spesifikk aktivitet
"""
import sys
import os

# Legg til backend-mappen i Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database.session import get_db
from app.database.models.activity import Activity

def check_specific_activity():
    """Sjekk power-verdi for aktivitet 19861351641"""
    
    print("🔍 SJEKKER POWER-VERDI FOR AKTIVITET 19861351641")
    print("=" * 60)
    
    db = next(get_db())
    
    try:
        # Hent spesifikk aktivitet
        activity = db.query(Activity).filter(Activity.activity_id == "19861351641").first()
        
        if not activity:
            print("❌ Kunne ikke finne aktivitet 19861351641")
            return
        
        print(f"Aktivitet ID: {activity.activity_id}")
        print(f"Navn: {activity.activity_name}")
        print(f"Gjennomsnittlig power: {activity.average_power} W")
        print(f"Maksimal power: {activity.max_power} W")
        print(f"Normalisert power: {activity.normalized_power} W")
        print(f"Dato: {activity.start_time}")
        print(f"Type: {activity.activity_type.type_key if activity.activity_type else 'None'}")
        print("-" * 40)
        
        # Sjekk også noen andre aktiviteter
        other_activities = db.query(Activity).filter(
            Activity.average_power.isnot(None)
        ).limit(3).all()
        
        print("📊 Andre aktiviteter med power-verdier:")
        for act in other_activities:
            print(f"ID: {act.activity_id}, Power: {act.average_power} W")
            
    except Exception as e:
        print(f"❌ Feil: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_specific_activity()