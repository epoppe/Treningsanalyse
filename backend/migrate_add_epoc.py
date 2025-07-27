#!/usr/bin/env python3
"""
Migrasjon for å legge til EPOC-kolonne i activities-tabellen
"""

import os
import sys
from sqlalchemy import text

# Legg til app-mappen i Python-stien
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.database.session import SessionLocal

def migrate_add_epoc():
    """Legger til EPOC-kolonne i activities-tabellen"""
    
    print("🔧 Starter migrasjon for å legge til EPOC-kolonne")
    
    db = SessionLocal()
    
    try:
        # Sjekk om kolonnen allerede eksisterer
        result = db.execute(text("""
            SELECT COUNT(*) 
            FROM pragma_table_info('activities') 
            WHERE name = 'epoc'
        """))
        
        column_exists = result.scalar() > 0
        
        if column_exists:
            print("✅ EPOC-kolonne eksisterer allerede")
            return
        
        # Legg til EPOC-kolonne
        print("📝 Legger til EPOC-kolonne...")
        db.execute(text("""
            ALTER TABLE activities 
            ADD COLUMN epoc REAL
        """))
        
        db.commit()
        print("✅ EPOC-kolonne lagt til")
        
        # Verifiser at kolonnen ble lagt til
        result = db.execute(text("""
            SELECT COUNT(*) 
            FROM pragma_table_info('activities') 
            WHERE name = 'epoc'
        """))
        
        if result.scalar() > 0:
            print("✅ EPOC-kolonne verifisert")
        else:
            print("❌ EPOC-kolonne ble ikke lagt til")
            
    except Exception as e:
        print(f"❌ Feil under migrasjon: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    migrate_add_epoc() 