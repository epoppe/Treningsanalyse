import sqlite3
from pathlib import Path

db_path = Path(__file__).parent / "data" / "treningsanalyse.db"

if db_path.exists():
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        # Sjekk kolonner i activities-tabellen
        cursor.execute("PRAGMA table_info(activities);")
        columns = cursor.fetchall()
        
        print("Kolonner i activities-tabellen:")
        body_battery_found = False
        
        for col in columns:
            col_name = col[1]
            col_type = col[2]
            print(f"  - {col_name} ({col_type})")
            
            if col_name == 'body_battery_start':
                body_battery_found = True
        
        print(f"\nbody_battery_start kolonne funnet: {body_battery_found}")
        
        if not body_battery_found:
            print("❌ body_battery_start kolonnen mangler!")
        else:
            print("✅ body_battery_start kolonnen eksisterer!")
            
    except Exception as e:
        print(f"Feil: {e}")
    finally:
        conn.close()
        
else:
    print(f"Database ikke funnet: {db_path}") 