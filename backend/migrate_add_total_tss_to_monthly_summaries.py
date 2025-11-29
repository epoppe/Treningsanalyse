#!/usr/bin/env python3
"""
Migrasjonsskript for å legge til total_tss-kolonnen i monthly_summaries-tabellen.
"""

import sqlite3
import os
import sys
from pathlib import Path

# Legg til app-mappen i Python-path
sys.path.append(str(Path(__file__).parent / 'app'))

def migrate_add_total_tss():
    """Legger til total_tss-kolonnen i monthly_summaries-tabellen."""
    
    # Finn database-filen
    db_path = Path(__file__).parent / 'data' / 'treningsanalyse.db'
    
    if not db_path.exists():
        print(f"[FEIL] Database-fil ikke funnet: {db_path}")
        return False
    
    try:
        # Koble til databasen
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("[INFO] Sjekker eksisterende kolonner i monthly_summaries-tabellen...")
        
        # Sjekk eksisterende kolonner
        cursor.execute("PRAGMA table_info(monthly_summaries)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'total_tss' in columns:
            print("[OK] total_tss-kolonnen eksisterer allerede")
            return True
        
        print("[INFO] Legger til total_tss-kolonnen...")
        
        # Legg til kolonnen
        cursor.execute("""
            ALTER TABLE monthly_summaries 
            ADD COLUMN total_tss FLOAT DEFAULT 0.0
        """)
        
        # Commit endringene
        conn.commit()
        
        print("[OK] total_tss-kolonnen lagt til")
        
        # Verifiser at kolonnen ble lagt til
        cursor.execute("PRAGMA table_info(monthly_summaries)")
        columns_after = [column[1] for column in cursor.fetchall()]
        
        if 'total_tss' in columns_after:
            print("[OK] Verifisert: total_tss-kolonnen er nå tilgjengelig")
            return True
        else:
            print("[FEIL] Kolonnen ble ikke lagt til")
            return False
            
    except sqlite3.Error as e:
        print(f"[FEIL] SQLite-feil: {e}")
        return False
    except Exception as e:
        print(f"[FEIL] Uventet feil: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    print("[INFO] Starter migrasjon for total_tss i monthly_summaries...")
    
    success = migrate_add_total_tss()
    
    if success:
        print("[OK] Migrasjon fullført")
        sys.exit(0)
    else:
        print("[FEIL] Migrasjon feilet")
        sys.exit(1)

