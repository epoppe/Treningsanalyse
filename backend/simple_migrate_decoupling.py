#!/usr/bin/env python3
"""
Forenklet database-migrasjon: Legger til decoupling_percent kolonne
"""

import os
import sqlite3

def migrate_add_decoupling_column():
    """Legger til decoupling_percent kolonne i activities-tabellen"""
    
    print("🔄 Starter database-migrasjon for decoupling_percent...")
    
    # Hent database-tilkobling (bruker riktig database-fil fra config)
    db_path = os.path.join(os.path.dirname(__file__), "data", "treningsanalyse.db")
    
    if not os.path.exists(db_path):
        print(f"❌ Database ikke funnet: {db_path}")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Sjekk om activities-tabellen eksisterer
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='activities';")
        table_exists = cursor.fetchone()
        
        if not table_exists:
            print("❌ Activities-tabell eksisterer ikke")
            conn.close()
            return False
        
        print("✅ Activities-tabell funnet")
        
        # Sjekk om kolonne allerede eksisterer
        cursor.execute("PRAGMA table_info(activities);")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'decoupling_percent' in columns:
            print("✅ decoupling_percent kolonne eksisterer allerede")
            conn.close()
            return True
        
        print(f"📊 Tabellen har {len(columns)} kolonner før migrasjon")
        
        # Legg til decoupling_percent kolonne
        print("➕ Legger til decoupling_percent kolonne...")
        cursor.execute("ALTER TABLE activities ADD COLUMN decoupling_percent REAL;")
        conn.commit()
        
        # Bekreft at kolonnen er lagt til
        cursor.execute("PRAGMA table_info(activities);")
        columns_after = cursor.fetchall()
        
        decoupling_column = None
        for col in columns_after:
            if col[1] == 'decoupling_percent':
                decoupling_column = col
                break
        
        if decoupling_column:
            print(f"✅ Kolonne lagt til: {decoupling_column[1]} ({decoupling_column[2]})")
            print(f"📊 Tabellen har nå {len(columns_after)} kolonner")
        else:
            print("❌ Kolonnen ble ikke lagt til som forventet")
            conn.close()
            return False
        
        conn.close()
        print("🎉 Database-migrasjon fullført!")
        return True
        
    except Exception as e:
        print(f"❌ Feil ved migrasjon: {e}")
        if 'conn' in locals():
            conn.close()
        return False

def activate_model_column():
    """Aktiverer decoupling_percent i Activity-modellen"""
    
    model_file = os.path.join(os.path.dirname(__file__), 'app', 'database', 'models', 'activity.py')
    
    try:
        with open(model_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Aktiver decoupling_percent kolonnen
        old_line = '    # decoupling_percent = Column(Float, nullable=True)  # TODO: Legg til når database-kolonne er opprettet'
        new_line = '    decoupling_percent = Column(Float, nullable=True)'
        
        if old_line in content:
            updated_content = content.replace(old_line, new_line)
            
            with open(model_file, 'w', encoding='utf-8') as f:
                f.write(updated_content)
            print("✅ Aktiverte decoupling_percent i Activity-modellen")
            return True
        else:
            print("⚠️  decoupling_percent allerede aktivert eller ikke funnet i modellen")
            return True
            
    except Exception as e:
        print(f"❌ Kunne ikke oppdatere Activity-modellen: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Starter decoupling-migrasjon...\n")
    
    # Steg 1: Legg til database-kolonne
    if migrate_add_decoupling_column():
        print("\n✅ Database-migrasjon fullført")
        
        # Steg 2: Aktiver kolonne i modell
        if activate_model_column():
            print("✅ SQLAlchemy-modell oppdatert")
            print("\n🎉 Decoupling-migrasjon fullført!")
            print("\n📋 Neste steg:")
            print("   1. Restart backend-serveren")
            print("   2. Test at /api/activities endpointet fungerer")
            print("   3. Test decoupling med database-caching")
        else:
            print("⚠️  Modell-oppdatering feilet, men database-migrasjon er ok")
            print("   Du kan aktivere caching manuelt senere")
    else:
        print("❌ Database-migrasjon feilet") 