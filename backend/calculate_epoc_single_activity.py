#!/usr/bin/env python3
"""
Script for å beregne EPOC for den ene manglende aktiviteten fra 2025
"""

import os
import sys
from datetime import datetime
from sqlalchemy import and_

# Legg til app-mappen i Python-stien
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.database.session import SessionLocal
from app.database.models.activity import Activity
import logging

# Konfigurer logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def calculate_epoc_for_activity(activity: Activity) -> float:
    """
    Beregner EPOC basert på tilgjengelige data for en aktivitet.
    """
    
    try:
        # Hvis EPOC allerede eksisterer, returner den
        if activity.epoc and activity.epoc > 0:
            return activity.epoc
        
        # Basis EPOC-verdi
        base_epoc = 50.0
        
        # Faktor 1: Training Effect
        training_effect_factor = 1.0
        if activity.total_training_effect:
            # Training Effect 1.0-5.0 mappes til faktor 0.5-2.0
            training_effect_factor = 0.5 + (activity.total_training_effect - 1.0) * 0.375
        
        # Faktor 2: Anaerobic Training Effect
        anaerobic_factor = 1.0
        if activity.total_anaerobic_training_effect:
            # Anaerobic TE 1.0-5.0 mappes til faktor 0.8-1.5
            anaerobic_factor = 0.8 + (activity.total_anaerobic_training_effect - 1.0) * 0.175
        
        # Faktor 3: Varighet
        duration_factor = 1.0
        if activity.duration:
            # Varighet i timer
            duration_hours = activity.duration / 3600
            # Normaliser til 1 time som baseline
            duration_factor = min(2.0, max(0.5, duration_hours))
        
        # Faktor 4: Intensitet basert på puls
        intensity_factor = 1.0
        if activity.average_heart_rate:
            # Anta max puls på 190 for beregning
            max_hr = 190
            hr_percentage = activity.average_heart_rate / max_hr
            # HR 60-90% mappes til intensitetsfaktor 0.7-1.8
            intensity_factor = 0.7 + (hr_percentage - 0.6) * 3.67
            intensity_factor = max(0.5, min(2.0, intensity_factor))
        
        # Faktor 5: Aktivitetstype
        activity_type_factor = 1.0
        if activity.activity_type and activity.activity_type.type_key:
            activity_type = activity.activity_type.type_key.lower()
            if 'running' in activity_type:
                activity_type_factor = 1.2  # Løping har høyere EPOC
            elif 'cycling' in activity_type:
                activity_type_factor = 1.0  # Sykling standard
            elif 'swimming' in activity_type:
                activity_type_factor = 0.9  # Svømming litt lavere
            elif 'walking' in activity_type:
                activity_type_factor = 0.6  # Gange mye lavere
        
        # Faktor 6: Hastighet (for løping)
        speed_factor = 1.0
        if activity.average_speed and activity.average_speed > 0:
            # Hastighet i m/s, normaliser til 3.0 m/s som baseline
            speed_factor = min(1.5, max(0.7, activity.average_speed / 3.0))
        
        # Beregn total EPOC
        epoc = base_epoc * training_effect_factor * anaerobic_factor * duration_factor * intensity_factor * activity_type_factor * speed_factor
        
        # Begrens til realistiske verdier (50-400)
        epoc = max(50, min(400, epoc))
        
        return round(epoc, 1)
        
    except Exception as e:
        logger.error(f"Feil ved beregning av EPOC for aktivitet {activity.activity_id}: {e}")
        return 50.0  # Fallback til minimum EPOC

def calculate_epoc_for_single_activity():
    """Beregner EPOC for den ene manglende aktiviteten fra 2025"""
    
    print("🔧 Beregner EPOC for manglende aktivitet fra 2025")
    
    db = SessionLocal()
    
    try:
        # Hent aktiviteten fra 1. juni 2025 som mangler EPOC
        activity_id = "19296135610"
        activity = db.query(Activity).filter(Activity.activity_id == activity_id).first()
        
        if not activity:
            print(f"❌ Aktivitet med ID {activity_id} ikke funnet")
            return
        
        print(f"📋 Aktivitet funnet:")
        print(f"   Navn: {activity.activity_name}")
        print(f"   Dato: {activity.start_time.strftime('%Y-%m-%d %H:%M')}")
        print(f"   Type: {activity.activity_type.type_key if activity.activity_type else 'N/A'}")
        print(f"   Varighet: {activity.duration/60:.1f} min")
        print(f"   Distanse: {activity.distance:.0f} m")
        print(f"   Gj.snitt puls: {activity.average_heart_rate}")
        print(f"   Training Effect: {activity.total_training_effect}")
        print(f"   Anaerobic TE: {activity.total_anaerobic_training_effect}")
        print(f"   Gj.snitt hastighet: {activity.average_speed:.2f} m/s")
        
        # Beregn EPOC
        print(f"\n🧮 Beregner EPOC...")
        new_epoc = calculate_epoc_for_activity(activity)
        
        print(f"✅ Beregnet EPOC: {new_epoc}")
        
        # Oppdater aktiviteten
        activity.epoc = new_epoc
        
        # Lagre til database
        db.commit()
        print(f"💾 EPOC lagret i database")
        
        # Verifiser at EPOC ble lagret
        updated_activity = db.query(Activity).filter(Activity.activity_id == activity_id).first()
        if updated_activity and updated_activity.epoc:
            print(f"✅ Verifisert: EPOC = {updated_activity.epoc}")
        else:
            print(f"❌ EPOC ble ikke lagret")
        
    except Exception as e:
        print(f"❌ Feil: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    calculate_epoc_for_single_activity() 