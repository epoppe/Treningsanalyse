#!/usr/bin/env python3
"""
Script for å legge til total_training_effect og total_anaerobic_training_effect kolonner
"""

import sqlite3
import os
from pathlib import Path

def migrate_add_training_effects():
    # Finn database-filen
    backend_dir = Path(__file__).parent
    db_path = backend_dir / "data" / "treningsanalyse.db"
    
    if not db_path.exists():
        print(f"Database ikke funnet: {db_path}")
        return False
    
    try:
        # Koble til databasen
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Sjekk om kolonnene allerede eksisterer
        cursor.execute("PRAGMA table_info(activities)")
        columns = [row[1] for row in cursor.fetchall()]
        
        # Legg til total_training_effect hvis den ikke eksisterer
        if 'total_training_effect' not in columns:
            cursor.execute("ALTER TABLE activities ADD COLUMN total_training_effect REAL")
            print("✓ Lagt til total_training_effect kolonne")
        else:
            print("✓ total_training_effect kolonne eksisterer allerede")
        
        # Legg til total_anaerobic_training_effect hvis den ikke eksisterer  
        if 'total_anaerobic_training_effect' not in columns:
            cursor.execute("ALTER TABLE activities ADD COLUMN total_anaerobic_training_effect REAL")
            print("✓ Lagt til total_anaerobic_training_effect kolonne")
        else:
            print("✓ total_anaerobic_training_effect kolonne eksisterer allerede")
        
        # Commit endringene
        conn.commit()
        
        # Verifiser at kolonnene ble lagt til
        cursor.execute("PRAGMA table_info(activities)")
        columns_after = [row[1] for row in cursor.fetchall()]
        
        print(f"\nBekreftelse - kolonner i activities-tabellen:")
        for col in ['training_stress_score', 'total_training_effect', 'total_anaerobic_training_effect']:
            if col in columns_after:
                print(f"  ✓ {col}")
            else:
                print(f"  ✗ {col} - MANGLER!")
        
        conn.close()
        print("\n✅ Training effect-kolonner lagt til vellykket!")
        return True
        
    except Exception as e:
        print(f"❌ Feil ved tillegging av kolonner: {e}")
        return False

if __name__ == "__main__":
    migrate_add_training_effects() 