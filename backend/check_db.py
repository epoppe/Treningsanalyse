import sqlite3
from pathlib import Path

def check_database():
    db_path = Path(__file__).parent / 'data' / 'treningsanalyse.db'
    if not db_path.exists():
        print(f"Database file not found: {db_path}")
        return
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Sjekk hvilke tabeller som finnes
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [table[0] for table in cursor.fetchall()]
    print("Tabeller i databasen:")
    for table in tables:
        print(f"  - {table}")
    
    # Sjekk activities-tabellen hvis den finnes
    if 'activities' in tables:
        cursor.execute("PRAGMA table_info(activities)")
        columns = cursor.fetchall()
        print("\nKolonner i activities-tabellen:")
        for col in columns:
            print(f"  - {col[1]} ({col[2]})")
    else:
        print("\nactivities-tabellen finnes ikke")
    
    # Sjekk activity_types-tabellen hvis den finnes
    if 'activity_types' in tables:
        cursor.execute("PRAGMA table_info(activity_types)")
        columns = cursor.fetchall()
        print("\nKolonner i activity_types-tabellen:")
        for col in columns:
            print(f"  - {col[1]} ({col[2]})")
    else:
        print("\nactivity_types-tabellen finnes ikke")
    
    conn.close()

if __name__ == "__main__":
    check_database() 