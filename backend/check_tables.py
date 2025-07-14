import sqlite3
from pathlib import Path

db_path = Path("data/treningsanalyse.db")

if db_path.exists():
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Hent alle tabeller
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    
    print("Tabeller i databasen:")
    for table in tables:
        print(f"  - {table[0]}")
    
    # Sjekk om activities-tabellen eksisterer
    if any('activities' in table[0].lower() for table in tables):
        print("\nFant activities-relatert tabell!")
        # Vis kolonner i activities-tabellen
        for table in tables:
            if 'activities' in table[0].lower():
                print(f"\nKolonner i {table[0]}:")
                cursor.execute(f"PRAGMA table_info({table[0]});")
                columns = cursor.fetchall()
                for col in columns:
                    print(f"  - {col[1]} ({col[2]})")
    else:
        print("\nIngen activities-tabell funnet!")
    
    conn.close()
else:
    print(f"Database ikke funnet: {db_path}") 