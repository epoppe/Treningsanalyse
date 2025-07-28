#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database.session import SessionLocal
from app.database.models.activity import Activity
from sqlalchemy import desc
from datetime import datetime

def main():
    db = SessionLocal()
    
    try:
        # Totalt antall aktiviteter
        total_count = db.query(Activity).count()
        print(f"Totalt antall aktiviteter: {total_count}")
        
        # Nyeste aktiviteter
        newest_activities = db.query(Activity).order_by(desc(Activity.start_time)).limit(5).all()
        print("\nNyeste aktiviteter:")
        for activity in newest_activities:
            print(f"  {activity.start_time} - {activity.activity_name}")
        
        # Eldste aktiviteter
        oldest_activities = db.query(Activity).order_by(Activity.start_time).limit(5).all()
        print("\nEldste aktiviteter:")
        for activity in oldest_activities:
            print(f"  {activity.start_time} - {activity.activity_name}")
        
        # Sjekk aktiviteter før 30.10.2024
        target_date = datetime(2024, 10, 30)
        older_activities = db.query(Activity).filter(Activity.start_time < target_date).count()
        print(f"\nAktiviteter før 30.10.2024: {older_activities}")
        
        if older_activities > 0:
            print("Eksempler på eldre aktiviteter:")
            old_examples = db.query(Activity).filter(Activity.start_time < target_date).order_by(desc(Activity.start_time)).limit(3).all()
            for activity in old_examples:
                print(f"  {activity.start_time} - {activity.activity_name}")
        
    except Exception as e:
        print(f"Feil: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    main() 