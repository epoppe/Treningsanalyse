#!/usr/bin/env python3
"""
Database initialization script for the new improved structure.
"""

import sys
from pathlib import Path

# Add the backend directory to the Python path
sys.path.append(str(Path(__file__).parent))

from app.database.models import Base
from app.database.session import engine
from app.database.models.activity import Activity, ActivityType, ActivityLap
from app.database.models.sleep import Sleep, SleepStage, HRV, RestingHeartRate, Weight
from app.database.models.summaries import DailySummary, WeeklySummary, MonthlySummary, YearlySummary, PersonalRecord

def create_database():
    """Create all database tables."""
    print("Creating database tables...")
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    print("✓ Database tables created successfully!")
    
    # Add some basic activity types
    from app.database.session import SessionLocal
    db = SessionLocal()
    
    try:
        # Check if activity types already exist
        existing_types = db.query(ActivityType).count()
        
        if existing_types == 0:
            print("Adding default activity types...")
            
            default_types = [
                {'type_key': 'running', 'type_name': 'Løping', 'parent_type_key': None},
                {'type_key': 'cycling', 'type_name': 'Sykling', 'parent_type_key': None},
                {'type_key': 'swimming', 'type_name': 'Svømming', 'parent_type_key': None},
                {'type_key': 'walking', 'type_name': 'Gåing', 'parent_type_key': None},
                {'type_key': 'hiking', 'type_name': 'Fotturer', 'parent_type_key': 'walking'},
                {'type_key': 'strength_training', 'type_name': 'Styrketrening', 'parent_type_key': None},
                {'type_key': 'yoga', 'type_name': 'Yoga', 'parent_type_key': None},
                {'type_key': 'other', 'type_name': 'Annet', 'parent_type_key': None}
            ]
            
            for activity_type_data in default_types:
                activity_type = ActivityType(**activity_type_data)
                db.add(activity_type)
            
            db.commit()
            print("✓ Default activity types added")
        else:
            print(f"✓ Activity types already exist ({existing_types} types)")
            
    except Exception as e:
        print(f"Error adding activity types: {e}")
        db.rollback()
    finally:
        db.close()

def main():
    """Main initialization function."""
    print("Initializing database...")
    print("=" * 50)
    
    try:
        create_database()
        
        print("\n" + "=" * 50)
        print("Database initialization completed successfully!")
        print("You can now start using the application with the new database structure.")
        
    except Exception as e:
        print(f"Database initialization failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 