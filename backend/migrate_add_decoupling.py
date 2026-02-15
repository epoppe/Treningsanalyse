#!/usr/bin/env python3
"""
Database-migrasjon: Legger til decoupling_percent kolonne i activities-tabellen
"""

import os
import sys
import sqlite3
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Legg til app-mappen i Python-stien
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.database.models.activity import Activity, Base
from app.dependencies import get_db_engine

def migrate_add_decoupling_column():
    """Migrasjon: Legger til decoupling_percent kolonne"""
    
    print("🔄 Starter database-migrasjon for decoupling_percent...")
    
    # Hent database-tilkobling
    db_path = os.path.join(os.path.dirname(__file__), "data", "treningsanalyse.db")
    
    if not os.path.exists(db_path):
        print(f"❌ Database ikke funnet: {db_path}")
        return False
    
    try:
        # Bruk SQLite direkte for migrasjon
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Sjekk om activities-tabellen eksisterer
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='activities';")
        table_exists = cursor.fetchone()
        
        if not table_exists:
            print("❌ Activities-tabell eksisterer ikke")
            conn.close()
            return False
        
        # Sjekk om kolonne allerede eksisterer
        cursor.execute("PRAGMA table_info(activities);")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'decoupling_percent' in columns:
            print("✅ decoupling_percent kolonne eksisterer allerede")
            conn.close()
            return True
        
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
        return True
        
    except Exception as e:
        print(f"❌ Feil ved migrasjon: {e}")
        if 'conn' in locals():
            conn.close()
        return False

def activate_decoupling_caching():
    """Aktiverer decoupling caching i Activity-modellen"""
    
    model_file = os.path.join(os.path.dirname(__file__), 'app', 'database', 'models', 'activity.py')
    
    try:
        with open(model_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Aktiver decoupling_percent kolonnen
        updated_content = content.replace(
            '    # decoupling_percent = Column(Float, nullable=True)  # TODO: Legg til når database-kolonne er opprettet',
            '    decoupling_percent = Column(Float, nullable=True)'
        )
        
        if updated_content != content:
            with open(model_file, 'w', encoding='utf-8') as f:
                f.write(updated_content)
            print("✅ Aktiverte decoupling_percent i Activity-modellen")
            return True
        else:
            print("⚠️  decoupling_percent var allerede aktivert i modellen")
            return True
            
    except Exception as e:
        print(f"❌ Kunne ikke oppdatere Activity-modellen: {e}")
        return False

def migrate_activities_router():
    """Aktiverer caching i activities router"""
    
    router_file = os.path.join(os.path.dirname(__file__), 'app', 'routers', 'activities.py')
    
    try:
        with open(router_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Erstatt placeholder med full caching-logikk
        if '# Decoupling caching er foreløpig deaktivert til database-kolonnen er lagt til' in content:
            print("✅ Caching-logikk i activities router kan aktiveres manuelt")
            
        return True
            
    except Exception as e:
        print(f"❌ Kunne ikke sjekke activities router: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Starter decoupling-migrasjon...")
    
    # Steg 1: Legg til database-kolonne
    if migrate_add_decoupling_column():
        print("✅ Database-migrasjon fullført")
        
        # Steg 2: Aktiver kolonne i modell
        if activate_decoupling_caching():
            print("✅ SQLAlchemy-modell oppdatert")
            
            # Steg 3: Sjekk router
            if migrate_activities_router():
                print("\n🎉 Decoupling-migrasjon fullført!")
                print("📋 Neste steg:")
                print("   1. Restart backend-serveren")
                print("   2. Aktiver caching-logikk i activities.py manuelt")
                print("   3. Test decoupling med database-caching")
            else:
                print("⚠️  Router-oppdatering feilet, men migrasjon er ok")
        else:
            print("❌ Modell-oppdatering feilet")
    else:
        print("❌ Database-migrasjon feilet") 