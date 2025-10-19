#!/usr/bin/env python3
"""Sjekker aktivitetstype data"""

import sys
from pathlib import Path

# Legg til backend-katalogen i path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.database.session import SessionLocal
from app.database.models.activity import Activity

def main():
    db = SessionLocal()
    try:
        activity = db.query(Activity).first()
        if not activity:
            print("Ingen aktiviteter funnet")
            return
            
        print(f"Activity ID: {activity.activity_id}")
        print(f"Activity Name: {activity.activity_name}")
        print(f"activity_type (relation): {activity.activity_type}")
        print(f"activity_type_id: {getattr(activity, 'activity_type_id', 'N/A')}")
        print(f"type: {getattr(activity, 'type', 'N/A')}")
        
        if activity.activity_type:
            print(f"\nActivityType attributes:")
            print(f"  type_name: {getattr(activity.activity_type, 'type_name', 'N/A')}")
            print(f"  type_key: {getattr(activity.activity_type, 'type_key', 'N/A')}")
            for attr in dir(activity.activity_type):
                if not attr.startswith('_') and not callable(getattr(activity.activity_type, attr)):
                    print(f"  {attr}: {getattr(activity.activity_type, attr)}")
        
        # Sjekk alle attributter
        print("\nAlle attributter som inneholder 'type':")
        for attr in dir(activity):
            if 'type' in attr.lower() and not attr.startswith('_'):
                try:
                    val = getattr(activity, attr)
                    if not callable(val):
                        print(f"  {attr}: {val}")
                except:
                    pass
            
    finally:
        db.close()

if __name__ == '__main__':
    main()
