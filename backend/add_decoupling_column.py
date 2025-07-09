#!/usr/bin/env python3
"""
Script for å legge til decoupling kolonne i activities-tabellen
"""

import os
import sqlite3

def add_decoupling_column():
    """Legger til decoupling kolonne i activities-tabellen"""
    
    db_path = os.path.join(os.path.dirname(__file__), "data", "activities.db")
    
    if not os.path.exists(db_path):
        print(f"❌ Database ikke funnet: {db_path}")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Sjekk om kolonne allerede eksisterer
        cursor.execute("PRAGMA table_info(activities);")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'decoupling_percent' in columns:
            print("✅ Decoupling kolonne eksisterer allerede")
            conn.close()
            return True
        
        # Legg til decoupling kolonne
        cursor.execute("ALTER TABLE activities ADD COLUMN decoupling_percent REAL;")
        conn.commit()
        
        print("✅ Lagt til decoupling_percent kolonne i activities-tabellen")
        
        # Bekreft at kolonnen er lagt til
        cursor.execute("PRAGMA table_info(activities);")
        columns = cursor.fetchall()
        print(f"📋 Tabellen har nå {len(columns)} kolonner")
        
        # Vis den nye kolonnen
        for col in columns:
            if col[1] == 'decoupling_percent':
                print(f"   ✅ {col[1]} ({col[2]})")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Feil ved endring av database: {e}")
        return False

if __name__ == "__main__":
    success = add_decoupling_column()
    if success:
        print("\n🎉 Database er klar for decoupling caching!")
    else:
        print("\n❌ Kunne ikke oppdatere database") 