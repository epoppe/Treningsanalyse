#!/usr/bin/env python3
"""
Script for å finne aktiviteten med +2.2% negative split
"""
import sys
import os
from datetime import datetime, timedelta

# Legg til backend-mappen i Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database.session import get_db
from app.database.models.activity import Activity, ActivityType

def find_activity_2_2_percent():
    """Finn aktiviteten med +2.2% negative split"""
    db = next(get_db())
    
    try:
        # Hent aktiviteter med negative split rundt 2.2%
        activities = db.query(Activity).join(ActivityType).filter(
            ActivityType.type_key.in_(['running', 'treadmill_running', 'trail_running']),
            Activity.negative_split_percent.between(2.0, 2.5)
        ).order_by(Activity.start_time.desc()).all()
        
        print("🔍 AKTIVITETER MED NEGATIVE SPLIT RUNDT 2.2%:")
        print("=" * 60)
        
        for activity in activities:
            activity_type = activity.activity_type.type_key if activity.activity_type else "Unknown"
            print(f"   ID: {activity.activity_id}")
            print(f"   Dato: {activity.start_time}")
            print(f"   Type: {activity_type}")
            print(f"   Negative Split: {activity.negative_split_percent:.2f}%")
            print(f"   Distanse: {activity.distance/1000:.2f} km")
            print(f"   Varighet: {activity.duration/60:.1f} min")
            print("-" * 40)
        
        # Hent også aktiviteter fra siste 30 dager med positive verdier
        thirty_days_ago = datetime.now() - timedelta(days=30)
        recent_positive = db.query(Activity).join(ActivityType).filter(
            ActivityType.type_key.in_(['running', 'treadmill_running', 'trail_running']),
            Activity.negative_split_percent > 0,
            Activity.start_time >= thirty_days_ago
        ).order_by(Activity.start_time.desc()).all()
        
        print(f"\n📊 AKTIVITETER FRA SISTE 30 DAGER MED POSITIVE SPLIT:")
        for activity in recent_positive:
            activity_type = activity.activity_type.type_key if activity.activity_type else "Unknown"
            print(f"   ID: {activity.activity_id}, Dato: {activity.start_time.strftime('%Y-%m-%d')}, Split: {activity.negative_split_percent:.2f}%")
            
    except Exception as e:
        print(f"❌ Feil: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    find_activity_2_2_percent() 