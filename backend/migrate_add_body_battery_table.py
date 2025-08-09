#!/usr/bin/env python3
"""
Script for å opprette Body Battery-tabellen i databasen
"""

import os
import sys
import sqlite3
from pathlib import Path

# Finn database-filen
project_root = Path(__file__).resolve().parent
db_path = project_root / "data" / "treningsanalyse.db"

def create_body_battery_table():
    """
    Oppretter body_battery-tabellen i databasen
    """
    if not db_path.exists():
        print(f"Database ikke funnet: {db_path}")
        return False
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Sjekk om tabellen allerede eksisterer
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='body_battery';")
        if cursor.fetchone():
            print("body_battery-tabellen eksisterer allerede!")
            return True
        
        # Opprett tabellen
        cursor.execute("""
            CREATE TABLE body_battery (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE NOT NULL,
                body_battery_charged REAL,
                body_battery_drained REAL,
                body_battery_charged_start REAL,
                body_battery_drained_start REAL,
                max_body_battery REAL,
                min_body_battery REAL,
                net_charge REAL,
                device_name VARCHAR(100),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Opprett indekser
        cursor.execute("CREATE INDEX idx_body_battery_date ON body_battery(date);")
        cursor.execute("CREATE INDEX idx_body_battery_created_at ON body_battery(created_at);")
        
        conn.commit()
        
        print("✅ Opprettet body_battery-tabellen med indekser")
        
        # Verifiser at tabellen ble opprettet
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='body_battery';")
        if cursor.fetchone():
            print("✅ Tabellen bekreftet opprettet")
            
            # Vis tabellstruktur
            cursor.execute("PRAGMA table_info(body_battery);")
            columns = cursor.fetchall()
            print("\n📋 Tabellstruktur:")
            for col in columns:
                print(f"  {col[1]} ({col[2]})")
            
            return True
        else:
            print("❌ Feil: Tabellen ble ikke opprettet")
            return False
            
    except Exception as e:
        print(f"❌ Feil ved opprettelse av tabell: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    print("🚀 Oppretter Body Battery-tabell...")
    success = create_body_battery_table()
    
    if success:
        print("✅ Body Battery-tabell opprettet vellykket!")
    else:
        print("❌ Feil ved opprettelse av Body Battery-tabell")
        sys.exit(1) 