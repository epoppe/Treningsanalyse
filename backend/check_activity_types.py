#!/usr/bin/env python3
"""
Script for å sjekke aktivitetstyper i databasen
"""
import sys
import os
from datetime import datetime, timedelta

# Legg til backend-mappen i Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database.session import get_db
from app.database.models.activity import Activity, ActivityType
from sqlalchemy import text

def check_activity_types():
    """Sjekk aktivitetstyper i databasen"""
    db = next(get_db())
    
    try:
        # Sjekk alle aktivitetstyper
        activity_types = db.query(ActivityType).all()
        print("📊 AKTIVITETSTYPER I DATABASEN:")
        for at in activity_types:
            print(f"   ID: {at.id}, Key: {at.type_key}, Name: {at.type_name}")
        
        # Sjekk løpeaktiviteter fra siste 30 dager
        thirty_days_ago = datetime.now() - timedelta(days=30)
        
        running_activities = db.query(Activity).join(ActivityType).filter(
            ActivityType.type_key.in_(['running', 'treadmill_running', 'trail_running']),
            Activity.start_time >= thirty_days_ago
        ).all()
        
        print(f"\n🏃‍♂️ LØPEAKTIVITETER FRA SISTE 30 DAGER: {len(running_activities)}")
        for activity in running_activities[:5]:  # Vis første 5
            activity_type = activity.activity_type.type_key if activity.activity_type else "Unknown"
            print(f"   ID: {activity.activity_id}, Type: {activity_type}, Date: {activity.start_time}")
        
        if len(running_activities) > 5:
            print(f"   ... og {len(running_activities) - 5} flere")
            
    except Exception as e:
        print(f"❌ Feil: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_activity_types() 