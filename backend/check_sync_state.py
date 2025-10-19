#!/usr/bin/env python3
"""
Sjekk SyncState-tabellen for å se om tilbakestillingen fungerte
"""
import sys
import os

# Legg til backend-mappen i Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database.session import SessionLocal
from app.database.models.sync_state import SyncState
from app.database.models.activity import Activity
from sqlalchemy import func

def check_sync_state():
    """Sjekk SyncState og aktiviteter i databasen"""
    db = SessionLocal()
    
    try:
        print("🔍 Sjekker SyncState-tabellen...")
        
        # Hent alle SyncState-oppføringer
        states = db.query(SyncState).all()
        
        if not states:
            print("⚠️ Ingen SyncState-oppføringer funnet!")
        else:
            for state in states:
                print(f"📊 {state.key}:")
                print(f"   - Sist synkronisert dato: {state.last_synced_date}")
                print(f"   - Sist synkronisert tidspunkt: {state.last_synced_at}")
                print(f"   - Metadata: {state.meta}")
                print()
        
        print("🔍 Sjekker aktiviteter i databasen...")
        
        # Hent statistikk om aktiviteter
        total_activities = db.query(func.count(Activity.id)).scalar()
        print(f"📈 Totalt antall aktiviteter: {total_activities}")
        
        if total_activities > 0:
            # Hent eldste og nyeste aktivitet
            oldest = db.query(Activity).order_by(Activity.start_time.asc()).first()
            newest = db.query(Activity).order_by(Activity.start_time.desc()).first()
            
            print(f"📅 Eldste aktivitet: {oldest.start_time} ({oldest.activity_name})")
            print(f"📅 Nyeste aktivitet: {newest.start_time} ({newest.activity_name})")
            
            # Sjekk aktiviteter før 11.11.2024
            from datetime import datetime
            cutoff_date = datetime(2024, 11, 11)
            before_cutoff = db.query(func.count(Activity.id)).filter(
                Activity.start_time < cutoff_date
            ).scalar()
            
            print(f"📊 Aktiviteter før 11.11.2024: {before_cutoff}")
            
            if before_cutoff > 0:
                print("✅ Det finnes aktiviteter før 11.11.2024 i databasen")
            else:
                print("❌ Ingen aktiviteter før 11.11.2024 funnet")
        
    except Exception as e:
        print(f"❌ Feil ved sjekk: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_sync_state()
