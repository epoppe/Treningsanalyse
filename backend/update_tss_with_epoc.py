#!/usr/bin/env python3
"""
Script for å oppdatere TSS-verdier med EPOC-baserte beregninger
"""

import os
import sys
from datetime import datetime, timedelta

# Legg til app-mappen i Python-stien
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.services.training_stress_service import TrainingStressService
from app.database.session import SessionLocal
from app.database.models.activity import Activity
from sqlalchemy import desc

def update_tss_with_epoc():
    """Oppdaterer TSS-verdier med EPOC-baserte beregninger"""
    
    print("🔧 Oppdaterer TSS-verdier med EPOC-baserte beregninger")
    
    db = SessionLocal()
    
    try:
        # Hent alle aktiviteter med EPOC-data som ikke har oppdatert TSS
        activities = db.query(Activity).filter(
            Activity.epoc.isnot(None),
            Activity.epoc > 0
        ).order_by(desc(Activity.start_time)).all()
        
        print(f"📊 Fant {len(activities)} aktiviteter med EPOC-data")
        
        if not activities:
            print("❌ Ingen aktiviteter med EPOC-data funnet")
            return
        
        # Initialiser service
        service = TrainingStressService(db)
        
        updated_count = 0
        skipped_count = 0
        
        for i, activity in enumerate(activities, 1):
            print(f"\n{i:3d}. Prosesserer {activity.activity_name}")
            print(f"     Dato: {activity.start_time.strftime('%Y-%m-%d %H:%M')}")
            print(f"     EPOC: {activity.epoc:.1f}")
            
            # Beregn ny TSS basert på EPOC
            new_tss = service.calculate_tss_for_activity(activity)
            
            # Sjekk om TSS allerede er oppdatert
            if activity.training_stress_score and abs(activity.training_stress_score - new_tss) < 0.1:
                print(f"     ⏭️  TSS allerede oppdatert: {activity.training_stress_score:.1f}")
                skipped_count += 1
                continue
            
            # Lagre gammel TSS for sammenligning
            old_tss = activity.training_stress_score
            
            # Oppdater TSS
            activity.training_stress_score = new_tss
            
            if old_tss is not None:
                print(f"     ✅ Oppdatert TSS: {old_tss:.1f} → {new_tss:.1f}")
                difference = new_tss - old_tss
                print(f"     📈 Endring: {difference:+.1f}")
            else:
                print(f"     ✅ Ny TSS: {new_tss:.1f}")
            
            updated_count += 1
        
        # Lagre endringene til databasen
        db.commit()
        
        print(f"\n✅ Fullført!")
        print(f"   Oppdatert: {updated_count} aktiviteter")
        print(f"   Hoppet over: {skipped_count} aktiviteter")
        print(f"   Total prosessert: {len(activities)} aktiviteter")
        
        # Vis sammendrag av TSS-verdier
        print(f"\n📊 SAMMENDRAG AV TSS-VERDIER:")
        recent_activities = db.query(Activity).filter(
            Activity.training_stress_score.isnot(None)
        ).order_by(desc(Activity.start_time)).limit(10).all()
        
        for activity in recent_activities:
            print(f"  {activity.activity_id}: {activity.activity_name}")
            print(f"    EPOC: {activity.epoc:.1f}, TSS: {activity.training_stress_score:.1f}")
        
    except Exception as e:
        print(f"❌ Feil: {e}")
        db.rollback()
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    update_tss_with_epoc() 