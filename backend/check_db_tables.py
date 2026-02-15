#!/usr/bin/env python3
"""
Script for å sjekke hvilke tabeller som finnes i SQLite-databasen
"""

import sqlite3
from pathlib import Path

def check_tables():
    db_path = Path(__file__).parent / 'data' / 'treningsanalyse.db'
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    
    print("Tabeller i databasen:")
    for table in tables:
        print(f"  - {table[0]}")
        
        # Vis kolonner for hver tabell
        cursor.execute(f"PRAGMA table_info({table[0]})")
        columns = cursor.fetchall()
        for column in columns:
            print(f"    {column[1]} ({column[2]})")
        print()
    
    conn.close()

if __name__ == "__main__":
    check_tables() 