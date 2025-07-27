#!/usr/bin/env python3
"""
Script for å sjekke manglende EPOC for 2025-aktiviteter
"""

import os
import sys
from datetime import datetime
from sqlalchemy import and_

# Legg til app-mappen i Python-stien
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.database.session import SessionLocal
from app.database.models.activity import Activity

def check_missing_epoc_2025():
    """Sjekker manglende EPOC for 2025-aktiviteter"""
    
    print("🔍 Sjekker manglende EPOC for 2025-aktiviteter")
    
    db = SessionLocal()
    
    try:
        # Hent aktiviteter fra 2025 uten EPOC
        start_date = datetime(2025, 1, 1)
        end_date = datetime(2026, 1, 1)
        
        activities_2025_without_epoc = db.query(Activity).filter(
            and_(
                Activity.start_time >= start_date,
                Activity.start_time < end_date,
                (Activity.epoc.is_(None) | (Activity.epoc == 0))
            )
        ).all()
        
        print(f"📊 Fant {len(activities_2025_without_epoc)} aktiviteter fra 2025 uten EPOC")
        
        if activities_2025_without_epoc:
            print(f"\n📋 AKTIVITETER FRA 2025 UTEN EPOC:")
            for activity in activities_2025_without_epoc:
                print(f"  {activity.start_time.strftime('%Y-%m-%d %H:%M')}: {activity.activity_name}")
                print(f"    ID: {activity.activity_id}")
                print(f"    Type: {activity.activity_type.type_key if activity.activity_type else 'N/A'}")
                print(f"    Varighet: {activity.duration/60:.1f} min")
                print(f"    Distanse: {activity.distance:.0f} m")
                print(f"    Gj.snitt puls: {activity.average_heart_rate}")
                print(f"    Training Effect: {activity.total_training_effect}")
                print(f"    Anaerobic TE: {activity.total_anaerobic_training_effect}")
                print()
        
        # Hent alle aktiviteter fra 2025 for sammenligning
        all_activities_2025 = db.query(Activity).filter(
            and_(
                Activity.start_time >= start_date,
                Activity.start_time < end_date
            )
        ).order_by(Activity.start_time.desc()).all()
        
        print(f"📊 Total aktiviteter fra 2025: {len(all_activities_2025)}")
        
        # Vis noen eksempler på aktiviteter med EPOC fra 2025
        print(f"\n📋 EKSEMPLER PÅ AKTIVITETER FRA 2025 MED EPOC:")
        sample_with_epoc = [a for a in all_activities_2025 if a.epoc and a.epoc > 0][:5]
        
        for activity in sample_with_epoc:
            print(f"  {activity.start_time.strftime('%Y-%m-%d %H:%M')}: {activity.activity_name} - EPOC: {activity.epoc}")
        
    except Exception as e:
        print(f"❌ Feil: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    check_missing_epoc_2025() 