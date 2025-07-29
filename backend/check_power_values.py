#!/usr/bin/env python3
"""
Script for å sjekke power-verdier direkte fra databasen
"""
import sys
import os

# Legg til backend-mappen i Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database.session import get_db
from app.database.models.activity import Activity, ActivityType
from sqlalchemy import and_

def check_power_values():
    """Sjekk power-verdier direkte fra databasen"""
    
    print("🔍 SJEKKER POWER-VERDIER FRA DATABASE")
    print("=" * 60)
    
    db = next(get_db())
    
    try:
        # Hent ID for løpingstypen
        running_type = db.query(ActivityType).filter(ActivityType.type_key == 'running').first()
        if not running_type:
            print("❌ Kunne ikke finne løpingstype")
            return
        
        # Hent løpeaktiviteter med power-verdier
        activities = db.query(Activity).filter(
            and_(
                Activity.activity_type_id == running_type.activity_type_id,
                Activity.average_power.isnot(None)
            )
        ).limit(5).all()
        
        print(f"📊 Fant {len(activities)} løpeaktiviteter med power-verdier:")
        print()
        
        for activity in activities:
            print(f"Aktivitet ID: {activity.activity_id}")
            print(f"Navn: {activity.activity_name}")
            print(f"Gjennomsnittlig power: {activity.average_power} W")
            print(f"Maksimal power: {activity.max_power} W")
            print(f"Normalisert power: {activity.normalized_power} W")
            print(f"Dato: {activity.start_time}")
            print("-" * 40)
        
        # Sjekk også noen aktiviteter uten power-verdier
        activities_without_power = db.query(Activity).filter(
            and_(
                Activity.activity_type_id == running_type.activity_type_id,
                Activity.average_power.is_(None)
            )
        ).limit(3).all()
        
        print(f"📊 Fant {len(activities_without_power)} løpeaktiviteter UTEN power-verdier:")
        print()
        
        for activity in activities_without_power:
            print(f"Aktivitet ID: {activity.activity_id}")
            print(f"Navn: {activity.activity_name}")
            print(f"Gjennomsnittlig power: {activity.average_power}")
            print(f"Dato: {activity.start_time}")
            print("-" * 40)
            
    except Exception as e:
        print(f"❌ Feil: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_power_values()