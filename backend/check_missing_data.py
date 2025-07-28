#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database.session import SessionLocal
from app.database.models.activity import Activity
from sqlalchemy import desc, func
from datetime import datetime

def main():
    db = SessionLocal()
    
    try:
        total_count = db.query(Activity).count()
        print(f"Totalt antall aktiviteter: {total_count}")
        
        # Sjekk manglende data
        print("\n=== Sjekker manglende data ===")
        
        # Aktiviteter uten EPOC
        no_epoc = db.query(Activity).filter(Activity.epoc.is_(None)).count()
        print(f"Aktiviteter uten EPOC: {no_epoc}")
        
        # Aktiviteter uten lactate threshold
        no_lactate = db.query(Activity).filter(Activity.lactate_threshold_speed.is_(None)).count()
        print(f"Aktiviteter uten lactate threshold: {no_lactate}")
        
        # Aktiviteter uten training effect
        no_aerobic_te = db.query(Activity).filter(Activity.total_training_effect.is_(None)).count()
        print(f"Aktiviteter uten aerobic training effect: {no_aerobic_te}")
        
        no_anaerobic_te = db.query(Activity).filter(Activity.total_anaerobic_training_effect.is_(None)).count()
        print(f"Aktiviteter uten anaerobic training effect: {no_anaerobic_te}")
        
        # Aktiviteter uten negative split
        no_negative_split = db.query(Activity).filter(Activity.negative_split_percent.is_(None)).count()
        print(f"Aktiviteter uten negative split: {no_negative_split}")
        
        # Aktiviteter uten decoupling
        no_decoupling = db.query(Activity).filter(Activity.decoupling_percent.is_(None)).count()
        print(f"Aktiviteter uten decoupling: {no_decoupling}")
        
        # Aktiviteter uten VO2 max
        no_vo2max = db.query(Activity).filter(Activity.vo2_max.is_(None)).count()
        print(f"Aktiviteter uten VO2 max: {no_vo2max}")
        
        # Aktiviteter uten average HR
        no_avg_hr = db.query(Activity).filter(Activity.average_heart_rate.is_(None)).count()
        print(f"Aktiviteter uten average HR: {no_avg_hr}")
        
        # Aktiviteter uten average speed
        no_avg_speed = db.query(Activity).filter(Activity.average_speed.is_(None)).count()
        print(f"Aktiviteter uten average speed: {no_avg_speed}")
        
        # Aktiviteter uten distance
        no_distance = db.query(Activity).filter(Activity.distance.is_(None)).count()
        print(f"Aktiviteter uten distance: {no_distance}")
        
        # Aktiviteter uten duration
        no_duration = db.query(Activity).filter(Activity.duration.is_(None)).count()
        print(f"Aktiviteter uten duration: {no_duration}")
        
        print("\n=== Eksempler på aktiviteter med manglende data ===")
        
        # Vis eksempler på aktiviteter uten EPOC
        if no_epoc > 0:
            print(f"\nEksempler på aktiviteter uten EPOC ({no_epoc} totalt):")
            examples = db.query(Activity).filter(Activity.epoc.is_(None)).order_by(desc(Activity.start_time)).limit(3).all()
            for activity in examples:
                print(f"  {activity.start_time} - {activity.activity_name} (ID: {activity.activity_id})")
        
        # Vis eksempler på aktiviteter uten lactate threshold
        if no_lactate > 0:
            print(f"\nEksempler på aktiviteter uten lactate threshold ({no_lactate} totalt):")
            examples = db.query(Activity).filter(Activity.lactate_threshold_speed.is_(None)).order_by(desc(Activity.start_time)).limit(3).all()
            for activity in examples:
                print(f"  {activity.start_time} - {activity.activity_name} (ID: {activity.activity_id})")
        
        # Sjekk aktiviteter før 30.10.2024 som mangler data
        target_date = datetime(2024, 10, 30)
        older_activities = db.query(Activity).filter(Activity.start_time < target_date).count()
        older_no_epoc = db.query(Activity).filter(Activity.start_time < target_date, Activity.epoc.is_(None)).count()
        older_no_lactate = db.query(Activity).filter(Activity.start_time < target_date, Activity.lactate_threshold_speed.is_(None)).count()
        
        print(f"\n=== Aktiviteter før 30.10.2024 ===")
        print(f"Totalt antall eldre aktiviteter: {older_activities}")
        print(f"Eldre aktiviteter uten EPOC: {older_no_epoc}")
        print(f"Eldre aktiviteter uten lactate threshold: {older_no_lactate}")
        
    except Exception as e:
        print(f"Feil: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    main() 