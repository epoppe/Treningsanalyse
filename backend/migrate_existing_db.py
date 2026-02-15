#!/usr/bin/env python3
"""
Database migration script for existing database.
"""

import sqlite3
import shutil
from pathlib import Path
from datetime import datetime

def backup_database():
    """Create a backup of the existing database."""
    backend_dir = Path(__file__).parent
    db_path = backend_dir / "data" / "treningsanalyse.db"
    if db_path.exists():
        backup_path = backend_dir / "data" / f"treningsanalyse_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2(db_path, backup_path)
        print(f"✓ Database backup created: {backup_path}")
        return backup_path
    return None

def migrate_activities_table():
    """Migrate activities table to new structure."""
    db_path = Path(__file__).parent / "data" / "treningsanalyse.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        print("Migrating activities table...")
        
        # Check current structure
        cursor.execute("PRAGMA table_info(activities)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'activity_id' in columns:
            print("✓ Activities table already migrated")
            return
        
        # Create new activities table with updated structure
        cursor.execute("""
            CREATE TABLE activities_new (
                activity_id VARCHAR(255) PRIMARY KEY,
                activity_name VARCHAR(255),
                description TEXT,
                start_time DATETIME,
                end_time DATETIME,
                distance FLOAT,
                duration FLOAT,
                moving_duration FLOAT,
                elapsed_duration FLOAT,
                calories FLOAT,
                average_speed FLOAT,
                max_speed FLOAT,
                average_pace FLOAT,
                average_heart_rate FLOAT,
                max_heart_rate FLOAT,
                min_heart_rate FLOAT,
                average_running_cadence FLOAT,
                max_running_cadence FLOAT,
                total_steps INTEGER,
                total_ascent FLOAT,
                total_descent FLOAT,
                min_elevation FLOAT,
                max_elevation FLOAT,
                average_power FLOAT,
                max_power FLOAT,
                normalized_power FLOAT,
                training_stress_score FLOAT,
                intensity_factor FLOAT,
                vo2_max FLOAT,
                lactate_threshold_heart_rate FLOAT,
                recovery_time INTEGER,
                weather_condition VARCHAR(100),
                temperature FLOAT,
                humidity FLOAT,
                wind_speed FLOAT,
                negative_split_percent FLOAT,
                running_economy FLOAT,
                decoupling_percent FLOAT,
                device_name VARCHAR(100),
                activity_type_id INTEGER,
                has_detailed_data BOOLEAN DEFAULT 0,
                detailed_metrics JSON,
                FOREIGN KEY (activity_type_id) REFERENCES activity_types (id)
            )
        """)
        
        # Copy data from old table to new table
        cursor.execute("""
            INSERT INTO activities_new (
                activity_id, activity_name, start_time, distance, duration, calories,
                average_speed, average_pace, average_heart_rate, average_running_cadence,
                vo2_max, activity_type_id, negative_split_percent,
                running_economy, decoupling_percent
            )
            SELECT 
                id, name, start_time, distance, duration, calories,
                average_speed, average_pace, average_hr, average_running_cadence,
                vo2_max, activity_type_id, negative_split_percent,
                running_economy, decoupling_percent
            FROM activities
        """)
        
        # Drop old table and rename new table
        cursor.execute("DROP TABLE activities")
        cursor.execute("ALTER TABLE activities_new RENAME TO activities")
        
        print("✓ Activities table migrated successfully")
        
    except Exception as e:
        print(f"✗ Error migrating activities table: {e}")
        conn.rollback()
        raise
    
    finally:
        conn.commit()
        conn.close()

def migrate_activity_types_table():
    """Add missing columns to activity_types table."""
    db_path = Path(__file__).parent / "data" / "treningsanalyse.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        print("Migrating activity_types table...")
        
        # Check if type_name column exists
        cursor.execute("PRAGMA table_info(activity_types)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'type_name' in columns:
            print("✓ Activity_types table already migrated")
            return
        
        # Add missing columns
        cursor.execute("ALTER TABLE activity_types ADD COLUMN type_name VARCHAR(100)")
        
        # Update existing records with default names
        cursor.execute("""
            UPDATE activity_types 
            SET type_name = CASE 
                WHEN type_key = 'running' THEN 'Løping'
                WHEN type_key = 'cycling' THEN 'Sykling'
                WHEN type_key = 'swimming' THEN 'Svømming'
                WHEN type_key = 'walking' THEN 'Gåing'
                WHEN type_key = 'hiking' THEN 'Fotturer'
                WHEN type_key = 'strength_training' THEN 'Styrketrening'
                WHEN type_key = 'yoga' THEN 'Yoga'
                ELSE 'Annet'
            END
        """)
        
        print("✓ Activity_types table migrated successfully")
        
    except Exception as e:
        print(f"✗ Error migrating activity_types table: {e}")
        conn.rollback()
        raise
    
    finally:
        conn.commit()
        conn.close()

def verify_migration():
    """Verify that the migration was successful."""
    print("Verifying migration...")
    
    try:
        # Test with SQLAlchemy models
        import sys
        from pathlib import Path
        sys.path.append(str(Path(__file__).parent))
        
        from app.database.session import SessionLocal
        from app.database.models.activity import Activity, ActivityType
        
        db = SessionLocal()
        
        # Test queries
        activity_count = db.query(Activity).count()
        activity_type_count = db.query(ActivityType).count()
        
        print(f"✓ Activities in database: {activity_count}")
        print(f"✓ Activity types in database: {activity_type_count}")
        
        # Test that we can query the first activity
        if activity_count > 0:
            first_activity = db.query(Activity).first()
            print(f"✓ First activity: {first_activity.activity_name} ({first_activity.activity_id})")
        
        db.close()
        return True
        
    except Exception as e:
        print(f"✗ Migration verification failed: {e}")
        return False

def main():
    """Main migration function."""
    print("Starting database migration...")
    print("=" * 50)
    
    try:
        # Step 1: Backup existing database
        backup_path = backup_database()
        
        # Step 2: Migrate activities table
        migrate_activities_table()
        
        # Step 3: Migrate activity_types table
        migrate_activity_types_table()
        
        # Step 4: Verify migration
        if verify_migration():
            print("\n" + "=" * 50)
            print("✓ Database migration completed successfully!")
            print("Your existing data has been preserved and updated to the new structure.")
            
            if backup_path:
                print(f"\nBackup file: {backup_path}")
                print("You can delete this backup file once you've verified everything works correctly.")
        else:
            print("\n" + "=" * 50)
            print("✗ Migration verification failed")
            print("Please check the logs and restore from backup if necessary.")
            
    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        print("Please restore from backup and try again.")
        return False
    
    return True

if __name__ == "__main__":
    success = main()
    if not success:
        exit(1) 