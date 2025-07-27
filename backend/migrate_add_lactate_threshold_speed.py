#!/usr/bin/env python3
"""
Migrasjonsskript for å legge til lactate_threshold_speed-kolonnen i activities-tabellen.
"""

import sqlite3
import os
import sys
from pathlib import Path

# Legg til app-mappen i Python-path
sys.path.append(str(Path(__file__).parent / 'app'))

def migrate_add_lactate_threshold_speed():
    """Legger til lactate_threshold_speed-kolonnen i activities-tabellen."""
    
    # Finn database-filen
    db_path = Path(__file__).parent / 'data' / 'treningsanalyse.db'
    
    if not db_path.exists():
        print(f"❌ Database-fil ikke funnet: {db_path}")
        return False
    
    try:
        # Koble til databasen
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("🔍 Sjekker eksisterende kolonner i activities-tabellen...")
        
        # Sjekk eksisterende kolonner
        cursor.execute("PRAGMA table_info(activities)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'lactate_threshold_speed' in columns:
            print("✅ lactate_threshold_speed-kolonnen eksisterer allerede")
            return True
        
        print("📝 Legger til lactate_threshold_speed-kolonnen...")
        
        # Legg til kolonnen
        cursor.execute("""
            ALTER TABLE activities 
            ADD COLUMN lactate_threshold_speed FLOAT
        """)
        
        # Commit endringene
        conn.commit()
        
        print("✅ lactate_threshold_speed-kolonnen lagt til")
        
        # Verifiser at kolonnen ble lagt til
        cursor.execute("PRAGMA table_info(activities)")
        columns_after = [column[1] for column in cursor.fetchall()]
        
        if 'lactate_threshold_speed' in columns_after:
            print("✅ Verifisert: lactate_threshold_speed-kolonnen er nå tilgjengelig")
            return True
        else:
            print("❌ Feil: Kolonnen ble ikke lagt til")
            return False
            
    except sqlite3.Error as e:
        print(f"❌ SQLite-feil: {e}")
        return False
    except Exception as e:
        print(f"❌ Uventet feil: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    print("🚀 Starter migrasjon for lactate_threshold_speed...")
    
    success = migrate_add_lactate_threshold_speed()
    
    if success:
        print("✅ Migrasjon fullført")
        sys.exit(0)
    else:
        print("❌ Migrasjon feilet")
        sys.exit(1) 