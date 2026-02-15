#!/usr/bin/env python3
"""
Migrasjonsskript for å legge til training_readiness_score kolonne i activities-tabellen.
"""

import sqlite3
import os
from pathlib import Path

def migrate_database():
    """Legger til training_readiness_score kolonne i activities-tabellen."""
    
    # Finn database-filen i data-mappen (portabel sti)
    db_path = Path(__file__).parent / "data" / "treningsanalyse.db"
    if not db_path.exists():
        print("Database-fil ikke funnet i data-mappen.")
        return False
    
    try:
        # Koble til databasen
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Sjekk om kolonnen allerede eksisterer
        cursor.execute("PRAGMA table_info(activities)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'training_readiness_score' not in columns:
            print("Legger til training_readiness_score kolonne...")
            
            # Legg til kolonnen
            cursor.execute("""
                ALTER TABLE activities 
                ADD COLUMN training_readiness_score REAL
            """)
            
            # Commit endringene
            conn.commit()
            print("✓ training_readiness_score kolonne lagt til.")
        else:
            print("✓ training_readiness_score kolonne eksisterer allerede.")
        
        # Vis tabellstruktur for å bekrefte
        cursor.execute("PRAGMA table_info(activities)")
        columns = cursor.fetchall()
        print("\nAktiviteter-tabell struktur:")
        for column in columns:
            print(f"  {column[1]} ({column[2]})")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"Feil under migrasjon: {e}")
        return False

if __name__ == "__main__":
    print("Starter migrasjon for training_readiness_score...")
    success = migrate_database()
    if success:
        print("\nMigrasjon fullført!")
    else:
        print("\nMigrasjon feilet!") 