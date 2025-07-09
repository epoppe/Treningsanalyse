#!/usr/bin/env python3
"""
Script for å legge til cache-kolonner i activities-tabellen
"""

import sqlite3
import os
from pathlib import Path

def add_cache_columns():
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
        
        # Legg til negative_split_percent hvis den ikke eksisterer
        if 'negative_split_percent' not in columns:
            cursor.execute("ALTER TABLE activities ADD COLUMN negative_split_percent REAL")
            print("✓ Lagt til negative_split_percent kolonne")
        else:
            print("✓ negative_split_percent kolonne eksisterer allerede")
        
        # Legg til running_economy hvis den ikke eksisterer  
        if 'running_economy' not in columns:
            cursor.execute("ALTER TABLE activities ADD COLUMN running_economy REAL")
            print("✓ Lagt til running_economy kolonne")
        else:
            print("✓ running_economy kolonne eksisterer allerede")
        
        # Commit endringene
        conn.commit()
        
        # Verifiser at kolonnene ble lagt til
        cursor.execute("PRAGMA table_info(activities)")
        columns_after = [row[1] for row in cursor.fetchall()]
        
        print(f"\nAllle kolonner i activities-tabellen:")
        for col in columns_after:
            print(f"  - {col}")
        
        conn.close()
        print("\n✅ Cache-kolonner lagt til vellykket!")
        return True
        
    except Exception as e:
        print(f"❌ Feil ved tillegging av kolonner: {e}")
        return False

if __name__ == "__main__":
    add_cache_columns() 