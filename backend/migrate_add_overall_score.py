#!/usr/bin/env python3
"""
Database migration script to add overall_score field to sleep table.
"""

import sys
import os
from pathlib import Path

# Add the backend directory to the Python path
sys.path.append(str(Path(__file__).parent))

from sqlalchemy import text
from app.database.session import SessionLocal

def migrate_add_overall_score():
    """Add overall_score field to the sleep table."""
    db = SessionLocal()
    
    try:
        print("\n[INFO] Starter migrering for sleep overall_score-felt...")
        
        # Check if column already exists
        result = db.execute(text("PRAGMA table_info(sleep)"))
        columns = [row[1] for row in result.fetchall()]
        
        if 'overall_score' not in columns:
            print("[INFO] Legger til kolonne 'overall_score' i sleep-tabellen...")
            db.execute(text("ALTER TABLE sleep ADD COLUMN overall_score REAL"))
            db.commit()
            print("[OK] Kolonne 'overall_score' lagt til")
        else:
            print("[INFO] Kolonne 'overall_score' eksisterer allerede")
        
        # Verify the changes
        result = db.execute(text("PRAGMA table_info(sleep)"))
        updated_columns = [row[1] for row in result.fetchall()]
        
        print("\n[INFO] Verifiserer endringer...")
        if 'overall_score' in updated_columns:
            print("[OK] overall_score kolonne er lagt til i sleep-tabellen")
            print("\n[SUCCESS] Migrering fullfort!")
            print("\nDet nye feltet:")
            print("  - overall_score: Overall score value fra sleep_scores (0-100)")
            return True
        else:
            print("[ERROR] Kolonnen ble ikke lagt til")
            return False
            
    except Exception as e:
        print(f"[ERROR] Feil under migrering: {e}")
        db.rollback()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    success = migrate_add_overall_score()
    sys.exit(0 if success else 1)

