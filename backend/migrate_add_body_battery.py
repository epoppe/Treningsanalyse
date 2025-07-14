import sqlite3
import os
import sys
from pathlib import Path

# Finn database-filen
project_root = Path(__file__).resolve().parent
db_path = project_root / "data" / "treningsanalyse.db"

def migrate_add_body_battery_column():
    """
    Legger til body_battery_start kolonne i activities-tabellen
    """
    if not db_path.exists():
        print(f"Database ikke funnet: {db_path}")
        return False
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Sjekk om kolonnen allerede eksisterer
        cursor.execute("PRAGMA table_info(activities);")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'body_battery_start' in columns:
            print("body_battery_start kolonne eksisterer allerede!")
            return True
        
        # Legg til den nye kolonnen
        cursor.execute("ALTER TABLE activities ADD COLUMN body_battery_start REAL;")
        conn.commit()
        
        print("✅ Lagt til body_battery_start kolonne i activities-tabellen")
        
        # Verifiser at kolonnen ble lagt til
        cursor.execute("PRAGMA table_info(activities);")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'body_battery_start' in columns:
            print("✅ Kolonnen bekreftet lagt til")
            return True
        else:
            print("❌ Feil: Kolonnen ble ikke lagt til")
            return False
            
    except Exception as e:
        print(f"❌ Feil ved migrering: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    print("Migrerer database for å legge til body_battery_start kolonne...")
    success = migrate_add_body_battery_column()
    
    if success:
        print("\n🎉 Database-migrering fullført!")
        print("Du kan nå starte backend-serveren på nytt.")
    else:
        print("\n❌ Database-migrering feilet!")
        sys.exit(1) 