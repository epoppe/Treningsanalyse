#!/usr/bin/env python3
"""
Script for å sjekke aktiviteter med positive negative split verdier
"""
import sys
import os
from datetime import datetime, timedelta

# Legg til backend-mappen i Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database.session import get_db
from app.database.models.activity import Activity, ActivityType

def check_positive_negative_splits():
    """Sjekk aktiviteter med positive negative split verdier"""
    db = next(get_db())
    
    try:
        # Hent alle aktiviteter med positive negative split verdier
        positive_splits = db.query(Activity).join(ActivityType).filter(
            ActivityType.type_key.in_(['running', 'treadmill_running', 'trail_running']),
            Activity.negative_split_percent > 0
        ).order_by(Activity.start_time.desc()).all()
        
        print("📊 AKTIVITETER MED POSITIVE NEGATIVE SPLIT VERDIER:")
        print("=" * 60)
        
        for activity in positive_splits:
            activity_type = activity.activity_type.type_key if activity.activity_type else "Unknown"
            print(f"   ID: {activity.activity_id}")
            print(f"   Dato: {activity.start_time}")
            print(f"   Type: {activity_type}")
            print(f"   Negative Split: {activity.negative_split_percent:.2f}%")
            print(f"   Distanse: {activity.distance/1000:.2f} km")
            print(f"   Varighet: {activity.duration/60:.1f} min")
            print("-" * 40)
        
        print(f"\n📈 TOTALT: {len(positive_splits)} aktiviteter med positiv split")
        
        # Hent også negative verdier for sammenligning
        negative_splits = db.query(Activity).join(ActivityType).filter(
            ActivityType.type_key.in_(['running', 'treadmill_running', 'trail_running']),
            Activity.negative_split_percent < 0
        ).order_by(Activity.start_time.desc()).limit(5).all()
        
        print(f"\n📊 EKSEMPLER PÅ NEGATIVE SPLIT VERDIER:")
        for activity in negative_splits:
            print(f"   ID: {activity.activity_id}, Split: {activity.negative_split_percent:.2f}%")
            
    except Exception as e:
        print(f"❌ Feil: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_positive_negative_splits() 