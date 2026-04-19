#!/usr/bin/env python3
"""
Script for å finne aktiviteter fra 21. og 23. juli som mangler FIT-data
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

def find_july_activities():
    """Finn aktiviteter fra 21. og 23. juli"""
    db = next(get_db())
    storage = DataStorage(settings.DATA_DIR)
    
    try:
        # Hent aktiviteter fra 21. og 23. juli 2025
        july_21 = datetime(2025, 7, 21)
        july_23 = datetime(2025, 7, 23)
        
        activities_21 = db.query(Activity).join(ActivityType).filter(
            ActivityType.type_key.in_(['running', 'treadmill_running', 'trail_running']),
            Activity.start_time >= july_21,
            Activity.start_time < july_21 + timedelta(days=1)
        ).all()
        
        activities_23 = db.query(Activity).join(ActivityType).filter(
            ActivityType.type_key.in_(['running', 'treadmill_running', 'trail_running']),
            Activity.start_time >= july_23,
            Activity.start_time < july_23 + timedelta(days=1)
        ).all()
        
        print("🔍 AKTIVITETER FRA 21. JULI 2025:")
        print("=" * 50)
        for activity in activities_21:
            activity_id = int(activity.activity_id)
            fit_data = storage.get_activity_details(activity_id)
            has_fit = "✅" if fit_data is not None and len(fit_data) > 0 else "❌"
            
            print(f"   ID: {activity_id}")
            print(f"   Dato: {activity.start_time}")
            print(f"   Distanse: {activity.distance/1000:.2f} km")
            print(f"   Varighet: {activity.duration/60:.1f} min")
            print(f"   FIT-data: {has_fit}")
            print(f"   Negative Split: {activity.negative_split_percent}")
            print(f"   Decoupling: {activity.decoupling_percent}")
            print("-" * 40)
        
        print("\n🔍 AKTIVITETER FRA 23. JULI 2025:")
        print("=" * 50)
        for activity in activities_23:
            activity_id = int(activity.activity_id)
            fit_data = storage.get_activity_details(activity_id)
            has_fit = "✅" if fit_data is not None and len(fit_data) > 0 else "❌"
            
            print(f"   ID: {activity_id}")
            print(f"   Dato: {activity.start_time}")
            print(f"   Distanse: {activity.distance/1000:.2f} km")
            print(f"   Varighet: {activity.duration/60:.1f} min")
            print(f"   FIT-data: {has_fit}")
            print(f"   Negative Split: {activity.negative_split_percent}")
            print(f"   Decoupling: {activity.decoupling_percent}")
            print("-" * 40)
        
        # Samle alle aktiviteter som mangler FIT-data
        missing_fit_activities = []
        for activity in activities_21 + activities_23:
            activity_id = int(activity.activity_id)
            fit_data = storage.get_activity_details(activity_id)
            if fit_data is None or len(fit_data) == 0:
                missing_fit_activities.append(activity)
        
        print(f"\n📊 SAMMENDRAG:")
        print(f"   Aktiviter 21. juli: {len(activities_21)}")
        print(f"   Aktiviter 23. juli: {len(activities_23)}")
        print(f"   Mangler FIT-data: {len(missing_fit_activities)}")
        
        if missing_fit_activities:
            print(f"\n🚀 AKTIVITETER SOM TRENGER FIT-DATA:")
            for activity in missing_fit_activities:
                print(f"   - {activity.activity_id} ({activity.start_time.strftime('%Y-%m-%d %H:%M')})")
            
    except Exception as e:
        print(f"❌ Feil: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    find_july_activities() 