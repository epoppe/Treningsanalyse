#!/usr/bin/env python3
"""
Debug script for å teste negative split beregningslogikk.
"""

import os
import sys
import pandas as pd
import numpy as np

# Legg til app-mappen i Python-stien
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.storage import DataStorage
from app.config import settings
from app.database.session import SessionLocal
from app.database.models.activity import Activity
from app.services.analysis_service import AnalysisService

def debug_negative_split_calculation():
    """Debug negative split beregning for en spesifikk aktivitet."""
    
    activity_id = 19842044922  # Aktivitet med +2.2% som brukeren mener er feil
    
    print(f"=== DEBUG NEGATIVE SPLIT BEREGNING FOR AKTIVITET {activity_id} ===")
    
    storage = DataStorage(settings.DATA_DIR)
    analysis_service = AnalysisService(storage)
    db = SessionLocal()
    
    try:
        # Hent aktivitet fra database
        activity = db.query(Activity).filter(Activity.activity_id == str(activity_id)).first()
        if not activity:
            print("❌ Aktivitet ikke funnet i database")
            return
        
        print(f"📊 Aktivitet: {activity.activity_name}")
        print(f"📅 Dato: {activity.start_time}")
        print(f"🏃‍♂️ Distanse: {activity.distance/1000:.2f} km")
        print(f"⏱️  Varighet: {activity.duration/60:.1f} min")
        print(f"📈 Nåværende negative split: {activity.negative_split_percent:.2f}%")
        
        # Hent FIT-data
        details_df = storage.get_activity_details(activity_id)
        if details_df is None or details_df.empty:
            print("❌ Ingen FIT-data tilgjengelig")
            return
        
        print(f"📊 FIT-data: {len(details_df)} datapunkter")
        
        # Filtrer ut rader med gyldig speed og timestamp data
        valid_data = details_df.dropna(subset=['speed', 'timestamp'])
        valid_data = valid_data[(valid_data['speed'] > 0)]
        
        print(f"✅ Gyldige datapunkter: {len(valid_data)}")
        
        if len(valid_data) < 20:
            print("❌ Ikke nok datapunkter")
            return
        
        # Sorter etter timestamp
        valid_data = valid_data.sort_values('timestamp')
        
        # Del i to halvdeler
        midpoint = len(valid_data) // 2
        first_half = valid_data.iloc[:midpoint]
        second_half = valid_data.iloc[midpoint:]
        
        print(f"📊 Første halvdel: {len(first_half)} datapunkter")
        print(f"📊 Andre halvdel: {len(second_half)} datapunkter")
        
        # Beregn gjennomsnittlig pace for hver halvdel (pace = 1000 / speed / 60)
        first_half_speed = first_half['speed'].mean()
        second_half_speed = second_half['speed'].mean()
        
        first_half_pace = 1000 / (first_half_speed * 60)  # min/km
        second_half_pace = 1000 / (second_half_speed * 60)  # min/km
        
        print(f"🏃‍♂️ Første halvdel:")
        print(f"   Gjennomsnittlig speed: {first_half_speed:.3f} m/s")
        print(f"   Gjennomsnittlig pace: {first_half_pace:.2f} min/km")
        
        print(f"🏃‍♂️ Andre halvdel:")
        print(f"   Gjennomsnittlig speed: {second_half_speed:.3f} m/s")
        print(f"   Gjennomsnittlig pace: {second_half_pace:.2f} min/km")
        
        # Test begge beregningsmetoder
        print(f"\n🧮 BEREGNINGSMETODER:")
        
        # Gammel metode: (first_half_pace - second_half_pace) / first_half_pace * 100
        old_method = ((first_half_pace - second_half_pace) / first_half_pace) * 100
        print(f"   Gammel metode: ({first_half_pace:.2f} - {second_half_pace:.2f}) / {first_half_pace:.2f} * 100 = {old_method:.2f}%")
        
        # Ny metode: (second_half_pace - first_half_pace) / first_half_pace * 100
        new_method = ((second_half_pace - first_half_pace) / first_half_pace) * 100
        print(f"   Ny metode: ({second_half_pace:.2f} - {first_half_pace:.2f}) / {first_half_pace:.2f} * 100 = {new_method:.2f}%")
        
        print(f"\n📊 SAMMENLIGNING:")
        print(f"   Database verdi: {activity.negative_split_percent:.2f}%")
        print(f"   Gammel metode: {old_method:.2f}%")
        print(f"   Ny metode: {new_method:.2f}%")
        
        # Test API-kallet
        print(f"\n🔍 TESTER API-KALL:")
        try:
            result = analysis_service.calculate_negative_split(activity_id, db)
            if result:
                print(f"   API resultat: {result['negative_split_percent']:.2f}%")
                print(f"   Beregningsmetode: {result['calculation_method']}")
            else:
                print("   ❌ API returnerte None")
        except Exception as e:
            print(f"   ❌ API feil: {e}")
        
        # Tolkning
        print(f"\n💡 TOLKNING:")
        if new_method < 0:
            print(f"   Negativ verdi ({new_method:.2f}%) = raskere andre halvdel = NEGATIV SPLIT ✓")
        else:
            print(f"   Positiv verdi ({new_method:.2f}%) = saktere andre halvdel = POSITIV SPLIT")
        
        if first_half_pace > second_half_pace:
            print(f"   Første halvdel ({first_half_pace:.2f} min/km) > Andre halvdel ({second_half_pace:.2f} min/km)")
            print(f"   → Løp raskere i andre halvdel = NEGATIV SPLIT")
        else:
            print(f"   Første halvdel ({first_half_pace:.2f} min/km) < Andre halvdel ({second_half_pace:.2f} min/km)")
            print(f"   → Løp saktere i andre halvdel = POSITIV SPLIT")
            
    except Exception as e:
        print(f"❌ Feil: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    debug_negative_split_calculation() 