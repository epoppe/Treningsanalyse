#!/usr/bin/env python3
"""
Script for å tvinge reberegning av negative split ved å nullstille cached verdi
"""
import sys
import os

# Legg til backend-mappen i Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database.session import get_db
from app.database.models.activity import Activity
from app.services.analysis_service import AnalysisService
from app.storage import DataStorage
from app.config import settings

def force_recalculate_activity():
    """Tvinge reberegning av negative split"""
    activity_id = 19842044922  # Aktivitet med feil +2.16% som burde være -2.16%
    
    print(f"🔧 TVINGER REBEREGNING FOR AKTIVITET {activity_id}")
    print("=" * 60)
    
    storage = DataStorage(settings.DATA_DIR)
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
        
        # Nullstill cached verdi
        old_value = activity.negative_split_percent
        activity.negative_split_percent = None
        db.commit()
        print(f"🔄 Nullstilt cached verdi: {old_value:.2f}% → None")
        
        # Beregn negative split på nytt
        result = analysis_service.calculate_negative_split(activity_id, db)
        
        if result and 'negative_split_percent' in result:
            new_value = result['negative_split_percent']
            print(f"📈 Ny negative split: {new_value:.2f}%")
            print(f"🔄 Endring: {old_value:.2f}% → {new_value:.2f}%")
            
            # Verifiser endringen
            db.refresh(activity)
            print(f"✅ Verifisert i database: {activity.negative_split_percent:.2f}%")
            
            if new_value < 0:
                print("✅ RIKTIG! Negativ verdi = raskere andre halvdel = NEGATIV SPLIT")
            else:
                print("❌ FORTSATT FEIL! Positiv verdi = saktere andre halvdel = POSITIV SPLIT")
            
        else:
            print("❌ Kunne ikke beregne negative split på nytt")
            
    except Exception as e:
        print(f"❌ Feil: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    force_recalculate_activity() 