#!/usr/bin/env python3
"""
Script for å sjekke hvilke tabeller som finnes i SQLite-databasen
"""

import os
import sqlite3

def check_database_tables():
    """Sjekk hvilke tabeller som finnes i SQLite-databasen"""
    
    db_path = os.path.join(os.path.dirname(__file__), "data", "activities.db")
    
    if not os.path.exists(db_path):
        print(f"❌ Database ikke funnet: {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Hent alle tabellnavn
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    
    print(f"📊 Database: {db_path}")
    print(f"🔍 Tabeller funnet: {len(tables)}")
    
    for table in tables:
        table_name = table[0]
        print(f"\n📋 Tabell: {table_name}")
        
        # Hent kolonneinformasjon
        cursor.execute(f"PRAGMA table_info({table_name});")
        columns = cursor.fetchall()
        
        print("   Kolonner:")
        for col in columns:
            col_id, col_name, col_type, not_null, default_val, primary_key = col
            print(f"     - {col_name} ({col_type})" + (" PRIMARY KEY" if primary_key else ""))
        
        # Hent antall rader
        cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
        row_count = cursor.fetchone()[0]
        print(f"   Antall rader: {row_count:,}")
    
    conn.close()

if __name__ == "__main__":
    check_database_tables() 