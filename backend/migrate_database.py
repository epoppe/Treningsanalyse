#!/usr/bin/env python3
"""
Database migration script for the new improved structure.
"""

import sys
import os
from pathlib import Path
from datetime import datetime
import sqlite3

# Add the backend directory to the Python path
sys.path.append(str(Path(__file__).parent))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.database.models import Base, Activity, ActivityType
from app.database.session import SessionLocal, engine

def backup_database():
    """Create a backup of the existing database."""
    backend_dir = Path(__file__).parent
    db_path = backend_dir / "data" / "treningsanalyse.db"
    if db_path.exists():
        backup_path = backend_dir / f"treningsanalyse_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        import shutil
        shutil.copy2(db_path, backup_path)
        print(f"Database backup created: {backup_path}")
        return backup_path
    return None

def migrate_existing_data():
    """Migrate data from old structure to new structure."""
    print("Starting data migration...")
    
    # Create connection to check existing structure
    conn = sqlite3.connect(str(Path(__file__).parent / "data" / "treningsanalyse.db"))
    cursor = conn.cursor()
    
    # Check if old 'activities' table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='activities'")
    if cursor.fetchone():
        print("Found existing activities table")
        
        # Get existing columns
        cursor.execute("PRAGMA table_info(activities)")
        existing_columns = [column[1] for column in cursor.fetchall()]
        print(f"Existing columns: {existing_columns}")
        
        # Check if we need to migrate
        if 'activity_id' not in existing_columns and 'id' in existing_columns:
            print("Migrating from old structure...")
            
            # Create new table with new structure
            cursor.execute("""
                CREATE TABLE activities_new (
                    activity_id TEXT PRIMARY KEY,
                    activity_name TEXT,
                    start_time DATETIME,
                    distance REAL,
                    duration REAL,
                    calories REAL,
                    average_heart_rate REAL,
                    max_heart_rate REAL,
                    average_speed REAL,
                    average_pace REAL,
                    average_running_cadence REAL,
                    total_ascent REAL,
                    total_descent REAL,
                    vo2_max REAL,
                    activity_type_id INTEGER,
                    negative_split_percent REAL,
                    running_economy REAL,
                    decoupling_percent REAL,
                    has_detailed_data BOOLEAN DEFAULT 0,
                    FOREIGN KEY (activity_type_id) REFERENCES activity_types (id)
                )
            """)
            
            # Map old columns to new columns
            column_mapping = {
                'id': 'activity_id',
                'name': 'activity_name',
                'average_hr': 'average_heart_rate'
            }
            
            # Copy data with column mapping
            old_columns = []
            new_columns = []
            
            for old_col in existing_columns:
                if old_col in column_mapping:
                    old_columns.append(old_col)
                    new_columns.append(column_mapping[old_col])
                elif old_col in ['start_time', 'distance', 'duration', 'calories', 'average_speed', 
                               'average_pace', 'average_running_cadence', 'vo2_max', 'activity_type_id',
                               'negative_split_percent', 'running_economy', 'decoupling_percent']:
                    old_columns.append(old_col)
                    new_columns.append(old_col)
            
            if old_columns:
                old_cols_str = ', '.join(old_columns)
                new_cols_str = ', '.join(new_columns)
                
                cursor.execute(f"""
                    INSERT INTO activities_new ({new_cols_str})
                    SELECT {old_cols_str} FROM activities
                """)
                
                # Drop old table and rename new table
                cursor.execute("DROP TABLE activities")
                cursor.execute("ALTER TABLE activities_new RENAME TO activities")
                
                print("Data migration completed successfully!")
            
        else:
            print("Database structure is already up to date")
    
    conn.commit()
    conn.close()

def create_new_tables():
    """Create all new tables."""
    print("Creating new database tables...")
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    print("New tables created successfully!")

def verify_migration():
    """Verify that the migration was successful."""
    print("Verifying migration...")
    
    db = SessionLocal()
    try:
        # Check if we can query activities
        activity_count = db.query(Activity).count()
        print(f"Activities in database: {activity_count}")
        
        # Check if we can query activity types
        activity_type_count = db.query(ActivityType).count()
        print(f"Activity types in database: {activity_type_count}")
        
        print("Migration verification completed successfully!")
        
    except Exception as e:
        print(f"Migration verification failed: {e}")
        return False
    finally:
        db.close()
    
    return True

def main():
    """Main migration function."""
    print("Starting database migration...")
    print("=" * 50)
    
    try:
        # Step 1: Backup existing database
        backup_path = backup_database()
        if backup_path:
            print(f"✓ Database backed up to: {backup_path}")
        
        # Step 2: Migrate existing data
        migrate_existing_data()
        print("✓ Data migration completed")
        
        # Step 3: Create new tables
        create_new_tables()
        print("✓ New tables created")
        
        # Step 4: Verify migration
        if verify_migration():
            print("✓ Migration verification successful")
            print("\n" + "=" * 50)
            print("Database migration completed successfully!")
            print("Your data has been preserved and new features are now available.")
            
            if backup_path:
                print(f"\nBackup file: {backup_path}")
                print("You can delete this backup file once you've verified everything works correctly.")
        else:
            print("✗ Migration verification failed")
            print("Please check the logs and restore from backup if necessary.")
            
    except Exception as e:
        print(f"Migration failed: {e}")
        print("Please restore from backup and try again.")
        sys.exit(1)

if __name__ == "__main__":
    main() 