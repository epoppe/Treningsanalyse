#!/usr/bin/env python3
"""
Script for å nullstille Body Battery cache etter oppdatering til FIT-data basert beregning
"""

import sqlite3
import os
from pathlib import Path

def reset_body_battery_cache():
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
        
        # Sjekk hvor mange aktiviteter som har Body Battery data
        cursor.execute("SELECT COUNT(*) FROM activities WHERE body_battery_start IS NOT NULL")
        count_before = cursor.fetchone()[0]
        
        print(f"🔍 Fant {count_before} aktiviteter med eksisterende Body Battery data")
        
        if count_before == 0:
            print("✅ Ingen Body Battery cache å nullstille")
            conn.close()
            return True
        
        # Nullstill Body Battery cache
        cursor.execute("UPDATE activities SET body_battery_start = NULL")
        rows_affected = cursor.rowcount
        
        # Commit endringene
        conn.commit()
        
        # Verifiser at dataene ble nullstilt
        cursor.execute("SELECT COUNT(*) FROM activities WHERE body_battery_start IS NOT NULL")
        count_after = cursor.fetchone()[0]
        
        print(f"✅ Nullstilte Body Battery cache for {rows_affected} aktiviteter")
        print(f"📊 Status: {count_before} → {count_after} aktiviteter med Body Battery data")
        
        if count_after == 0:
            print("🎯 Alle Body Battery verdier vil nå bli re-beregnet med FIT-data basert logikk")
        else:
            print(f"⚠️  Advarsel: {count_after} aktiviteter har fortsatt Body Battery data")
        
        conn.close()
        print("\n✅ Body Battery cache nullstilt vellykket!")
        print("💡 Start backend-serveren på nytt for å se nye beregninger")
        return True
        
    except Exception as e:
        print(f"❌ Feil ved nullstilling av Body Battery cache: {e}")
        return False

if __name__ == "__main__":
    reset_body_battery_cache() 