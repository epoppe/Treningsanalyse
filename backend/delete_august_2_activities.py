#!/usr/bin/env python3
"""
Script for å fjerne alle aktiviteter fra 2. august 2025 fra databasen.
Dette er for testing av synkroniseringsfunksjonalitet.
"""

import sys
import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, and_
from sqlalchemy.orm import sessionmaker

# Legg til backend/app i Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.database.models.activity import Activity
from app.database.session import get_db
from app.config import settings

def delete_august_2_activities():
    """Fjern alle aktiviteter fra 2. august 2025."""
    
    # Opprett database-tilkobling
    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    db = SessionLocal()
    
    try:
        # Definer start- og sluttdato for 2. august 2025
        start_date = datetime(2025, 8, 2, 0, 0, 0, tzinfo=timezone.utc)
        end_date = datetime(2025, 8, 2, 23, 59, 59, tzinfo=timezone.utc)
        
        print(f"Leter etter aktiviteter fra {start_date} til {end_date}...")
        
        # Finn alle aktiviteter fra 2. august 2025
        activities_to_delete = db.query(Activity).filter(
            and_(
                Activity.start_time >= start_date,
                Activity.start_time <= end_date
            )
        ).all()
        
        if not activities_to_delete:
            print("Ingen aktiviteter funnet fra 2. august 2025.")
            return
        
        print(f"Fant {len(activities_to_delete)} aktiviteter fra 2. august 2025:")
        
        # Vis aktivitetene som skal slettes
        for activity in activities_to_delete:
            print(f"  - {activity.activity_id}: {activity.activity_name} ({activity.start_time})")
        
        # Bekreft sletting
        confirm = input(f"\nEr du sikker på at du vil slette {len(activities_to_delete)} aktiviteter? (ja/nei): ")
        
        if confirm.lower() in ['ja', 'yes', 'y']:
            # Slett aktivitetene
            for activity in activities_to_delete:
                db.delete(activity)
            
            # Commit endringene
            db.commit()
            print(f"✓ Slettet {len(activities_to_delete)} aktiviteter fra 2. august 2025.")
        else:
            print("Sletting avbrutt.")
            db.rollback()
    
    except Exception as e:
        print(f"Feil ved sletting av aktiviteter: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    delete_august_2_activities() 