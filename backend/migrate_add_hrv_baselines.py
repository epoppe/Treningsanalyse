#!/usr/bin/env python3
"""
Database migration script to add baseline fields to HRV table.
"""

import sys
import os
from pathlib import Path

# Add the backend directory to the Python path
sys.path.append(str(Path(__file__).parent))

from sqlalchemy import text
from app.database.session import SessionLocal

def migrate_add_hrv_baselines():
    """Add baseline fields to the HRV table."""
    db = SessionLocal()
    
    try:
        print("\n[INFO] Starter migrering for HRV baseline-felter...")
        
        # Check if columns already exist
        result = db.execute(text("PRAGMA table_info(hrv)"))
        columns = [row[1] for row in result.fetchall()]
        
        new_columns = {
            'baseline_balanced_lower': 'FLOAT',
            'baseline_balanced_upper': 'FLOAT',
            'baseline_low_upper': 'FLOAT',
            'status': 'VARCHAR(50)'
        }
        
        for column_name, column_type in new_columns.items():
            if column_name not in columns:
                print(f"[INFO] Legger til kolonne '{column_name}' i HRV-tabellen...")
                db.execute(text(f"ALTER TABLE hrv ADD COLUMN {column_name} {column_type}"))
                db.commit()
                print(f"[OK] Kolonne '{column_name}' lagt til")
            else:
                print(f"[INFO] Kolonne '{column_name}' eksisterer allerede")
        
        # Verify the changes
        result = db.execute(text("PRAGMA table_info(hrv)"))
        updated_columns = [row[1] for row in result.fetchall()]
        
        print("\n[INFO] Verifiserer endringer...")
        all_present = all(col in updated_columns for col in new_columns.keys())
        
        if all_present:
            print("[OK] Alle nye kolonner er lagt til i HRV-tabellen")
            print("\n[SUCCESS] Migrering fullfort!")
            print("\nDe nye feltene:")
            print("  - baseline_balanced_lower: Nedre grense for normalområde")
            print("  - baseline_balanced_upper: Øvre grense for normalområde")
            print("  - baseline_low_upper: Øvre grense for lavt område")
            print("  - status: HRV status fra Garmin")
            return True
        else:
            print("[ERROR] Ikke alle kolonner ble lagt til")
            return False
            
    except Exception as e:
        print(f"[ERROR] Feil under migrering: {e}")
        db.rollback()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    success = migrate_add_hrv_baselines()
    sys.exit(0 if success else 1)

