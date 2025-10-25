#!/usr/bin/env python3
import sys
from pathlib import Path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.database.session import SessionLocal
from app.database.models.activity import Activity, ActivityType
from sqlalchemy.orm import joinedload

db = SessionLocal()
try:
    # Hent en aktivitet med eager loading
    activity = db.query(Activity).options(
        joinedload(Activity.activity_type)
    ).first()
    
    if activity:
        print(f"Activity: {activity.activity_name}")
        print(f"activity_type object: {activity.activity_type}")
        print(f"activity_type_id: {activity.activity_type_id}")
        
        if activity.activity_type:
            print(f"type_name: {activity.activity_type.type_name}")
            print(f"type_key: {activity.activity_type.type_key}")
        else:
            print("activity_type is None")
    
    # Sjekk hva som er i ActivityType-tabellen
    print("\n--- ActivityType table ---")
    types = db.query(ActivityType).limit(5).all()
    for t in types:
        print(f"ID: {t.id}, type_key: {t.type_key}, type_name: {t.type_name}")
finally:
    db.close()




