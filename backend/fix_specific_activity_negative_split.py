#!/usr/bin/env python3
"""
Script for å fikse spesifikk aktivitet med feil negative split verdi
"""
import sys
import os

# Legg til backend-mappen i Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database.session import get_db
from app.database.models.activity import Activity
from app.services.analysis_service import AnalysisService
from app.storage import DataStorage

def fix_specific_activity():
    """Fikse spesifikk aktivitet med feil negative split"""
    activity_id = 19842044922  # Aktivitet med feil +2.16% som burde være -2.16%
    
    print(f"🔧 FIKSER AKTIVITET {activity_id} MED FEIL NEGATIVE SPLIT")
    print("=" * 60)
    
    storage = DataStorage()
    analysis_service = AnalysisService(storage)
    db = next(get_db())
    
    try:
        # Hent aktivitet fra database
        activity = db.query(Activity).filter(Activity.activity_id == str(activity_id)).first()
        if not activity:
            print("❌ Aktivitet ikke funnet i database")
            return
        
        print(f"📊 Aktivitet: {activity.activity_name}")
        print(f"📅 Dato: {activity.start_time}")
        print(f"🏃‍♂️ Distanse: {activity.distance/1000:.2f} km")
        print(f"📈 Gammel negative split: {activity.negative_split_percent:.2f}%")
        
        # Beregn negative split på nytt
        result = analysis_service.calculate_negative_split(activity_id, db)
        
        if result and 'negative_split_percent' in result:
            new_value = result['negative_split_percent']
            print(f"📈 Ny negative split: {new_value:.2f}%")
            print(f"🔄 Endring: {activity.negative_split_percent:.2f}% → {new_value:.2f}%")
            
            # Oppdater databasen
            activity.negative_split_percent = new_value
            db.commit()
            
            print("✅ Aktivitet oppdatert i database!")
            
            # Verifiser endringen
            db.refresh(activity)
            print(f"✅ Verifisert: {activity.negative_split_percent:.2f}%")
            
        else:
            print("❌ Kunne ikke beregne negative split på nytt")
            
    except Exception as e:
        print(f"❌ Feil: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    fix_specific_activity() 