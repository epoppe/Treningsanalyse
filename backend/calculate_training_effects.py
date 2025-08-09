#!/usr/bin/env python3
"""
Script for å beregne manglende aerob og anaerob effekt-verdier basert på eksisterende FIT-data
"""

import os
import sys
import logging
from datetime import datetime
from sqlalchemy import and_, or_

# Legg til app-mappen i Python-stien
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.database.session import SessionLocal
from app.database.models.activity import Activity
from app.storage import get_storage

# Konfigurer logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def calculate_training_effects_from_fit_data(activity: Activity, storage) -> tuple[float, float]:
    """
    Beregner aerob og anaerob effekt basert på FIT-data og andre tilgjengelige målinger.
    
    Returns:
        tuple: (aerob_effekt, anaerob_effekt)
    """
    
    try:
        # Hvis verdiene allerede eksisterer, returner dem
        if activity.total_training_effect and activity.total_anaerobic_training_effect:
            return activity.total_training_effect, activity.total_anaerobic_training_effect
        
        # Basis verdier
        aerobic_effect = 1.0  # Minimum aerob effekt
        anaerobic_effect = 1.0  # Minimum anaerob effekt
        
        # Faktor 1: Intensitet basert på puls
        if activity.average_heart_rate:
            # Anta max puls på 190 for beregning
            max_hr = 190
            hr_percentage = activity.average_heart_rate / max_hr
            
            # HR 50-95% mappes til aerob effekt 1.0-5.0
            if hr_percentage >= 0.5:
                aerobic_effect = 1.0 + (hr_percentage - 0.5) * 8.9  # 1.0 til 5.0
                aerobic_effect = max(1.0, min(5.0, aerobic_effect))
            
            # HR 70-95% mappes til anaerob effekt 1.0-5.0
            if hr_percentage >= 0.7:
                anaerobic_effect = 1.0 + (hr_percentage - 0.7) * 16.0  # 1.0 til 5.0
                anaerobic_effect = max(1.0, min(5.0, anaerobic_effect))
        
        # Faktor 2: Varighet
        if activity.duration:
            duration_hours = activity.duration / 3600
            
            # Lengre aktiviteter har høyere aerob effekt
            if duration_hours >= 0.5:  # Minimum 30 minutter
                duration_factor = min(1.5, duration_hours / 2.0)  # Normaliser til 2 timer
                aerobic_effect *= duration_factor
                aerobic_effect = max(1.0, min(5.0, aerobic_effect))
        
        # Faktor 3: Hastighet (for løping)
        if activity.average_speed and activity.average_speed > 0:
            # Hastighet i m/s, normaliser til 3.0 m/s som baseline
            speed_factor = activity.average_speed / 3.0
            speed_factor = max(0.5, min(2.0, speed_factor))
            
            # Høyere hastighet øker både aerob og anaerob effekt
            aerobic_effect *= speed_factor
            anaerobic_effect *= speed_factor
            aerobic_effect = max(1.0, min(5.0, aerobic_effect))
            anaerobic_effect = max(1.0, min(5.0, anaerobic_effect))
        
        # Faktor 4: Aktivitetstype
        if activity.activity_type and activity.activity_type.type_key:
            activity_type = activity.activity_type.type_key.lower()
            
            if 'running' in activity_type:
                # Løping har høyere effekt
                aerobic_effect *= 1.2
                anaerobic_effect *= 1.1
            elif 'cycling' in activity_type:
                # Sykling standard
                pass
            elif 'swimming' in activity_type:
                # Svømming litt lavere
                aerobic_effect *= 0.9
                anaerobic_effect *= 0.8
            elif 'walking' in activity_type:
                # Gange mye lavere
                aerobic_effect *= 0.6
                anaerobic_effect *= 0.5
            
            aerobic_effect = max(1.0, min(5.0, aerobic_effect))
            anaerobic_effect = max(1.0, min(5.0, anaerobic_effect))
        
        # Faktor 5: Kalorier (hvis tilgjengelig)
        if activity.calories and activity.calories > 0:
            # Høyere kaloriforbruk indikerer høyere intensitet
            calorie_factor = min(1.5, activity.calories / 500.0)  # Normaliser til 500 kcal
            aerobic_effect *= calorie_factor
            anaerobic_effect *= calorie_factor
            aerobic_effect = max(1.0, min(5.0, aerobic_effect))
            anaerobic_effect = max(1.0, min(5.0, anaerobic_effect))
        
        # Faktor 6: Høydeforskjell (hvis tilgjengelig)
        if activity.total_ascent and activity.total_ascent > 0:
            # Høydeforskjell øker intensiteten
            ascent_factor = min(1.3, 1.0 + (activity.total_ascent / 1000.0))  # Normaliser til 1000m
            aerobic_effect *= ascent_factor
            anaerobic_effect *= ascent_factor
            aerobic_effect = max(1.0, min(5.0, aerobic_effect))
            anaerobic_effect = max(1.0, min(5.0, anaerobic_effect))
        
        # Faktor 7: Kadanse (for løping)
        if activity.average_running_cadence and activity.average_running_cadence > 0:
            # Høyere kadanse indikerer høyere intensitet
            cadence_factor = min(1.2, activity.average_running_cadence / 180.0)  # Normaliser til 180 spm
            aerobic_effect *= cadence_factor
            anaerobic_effect *= cadence_factor
            aerobic_effect = max(1.0, min(5.0, aerobic_effect))
            anaerobic_effect = max(1.0, min(5.0, anaerobic_effect))
        
        # Begrens verdiene til realistiske områder
        aerobic_effect = max(1.0, min(5.0, aerobic_effect))
        anaerobic_effect = max(1.0, min(5.0, anaerobic_effect))
        
        return round(aerobic_effect, 1), round(anaerobic_effect, 1)
        
    except Exception as e:
        logger.error(f"Feil ved beregning av Training Effects for aktivitet {activity.activity_id}: {e}")
        return 1.0, 1.0  # Fallback til minimum verdier

def calculate_missing_training_effects():
    """Beregner manglende aerob og anaerob effekt-verdier for alle aktiviteter"""
    
    db = SessionLocal()
    storage = get_storage()
    
    try:
        # Finn aktiviteter som mangler aerob eller anaerob effekt
        activities_without_effects = db.query(Activity).filter(
            or_(
                Activity.total_training_effect.is_(None),
                Activity.total_anaerobic_training_effect.is_(None)
            )
        ).all()
        
        logger.info(f"Fant {len(activities_without_effects)} aktiviteter som mangler Training Effect verdier")
        
        if not activities_without_effects:
            logger.info("Alle aktiviteter har allerede Training Effect verdier")
            return
        
        updated_count = 0
        failed_count = 0
        
        for i, activity in enumerate(activities_without_effects, 1):
            logger.info(f"Prosesserer aktivitet {i}/{len(activities_without_effects)}: {activity.activity_id} - {activity.activity_name}")
            
            try:
                # Beregn Training Effects
                aerobic_effect, anaerobic_effect = calculate_training_effects_from_fit_data(activity, storage)
                
                # Oppdater aktiviteten
                activity.total_training_effect = aerobic_effect
                activity.total_anaerobic_training_effect = anaerobic_effect
                
                logger.info(f"✅ Oppdatert aktivitet {activity.activity_id}: "
                          f"Aerobic={aerobic_effect}, Anaerobic={anaerobic_effect}")
                
                updated_count += 1
                
            except Exception as e:
                logger.error(f"❌ Feil ved prosessering av aktivitet {activity.activity_id}: {e}")
                failed_count += 1
        
        # Lagre endringene til databasen
        db.commit()
        
        logger.info(f"\n🎉 Fullført! Oppdatert {updated_count} aktiviteter, {failed_count} feilet")
        
        # Vis et sammendrag av de oppdaterte verdiene
        logger.info(f"\n📊 SAMMENDRAG AV OPPDATERTE VERDIER:")
        for activity in activities_without_effects[:10]:  # Vis første 10
            logger.info(f"  {activity.activity_id}: Aerobic={activity.total_training_effect}, "
                       f"Anaerobic={activity.total_anaerobic_training_effect}")
        
        if len(activities_without_effects) > 10:
            logger.info(f"  ... og {len(activities_without_effects) - 10} flere aktiviteter")
        
    except Exception as e:
        logger.error(f"Feil ved beregning av Training Effects: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    logger.info("🚀 Starter beregning av manglende Training Effect verdier...")
    calculate_missing_training_effects()
    logger.info("✅ Ferdig!") 