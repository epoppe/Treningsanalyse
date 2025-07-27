#!/usr/bin/env python3
"""
Script for å beregne EPOC for historiske aktiviteter fra 1. juni 2025 og tidligere, tilbake til januar 2021
"""

import os
import sys
from datetime import datetime, date
from sqlalchemy import and_, func

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
    
    EPOC-beregning basert på:
    - Training Effect (aerob og anaerob)
    - Varighet
    - Intensitet (basert på puls og hastighet)
    - Aktivitetstype
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

def calculate_historical_epoc():
    """Beregner EPOC for historiske aktiviteter"""
    
    print("🔧 Starter beregning av EPOC for historiske aktiviteter")
    print("📅 Periode: 1. juni 2025 og tidligere, tilbake til januar 2021")
    
    db = SessionLocal()
    
    try:
        # Definer datogrenser
        end_date = datetime(2025, 6, 1)  # 1. juni 2025
        start_date = datetime(2021, 1, 1)  # Januar 2021
        
        # Hent aktiviteter i perioden som ikke har EPOC eller har EPOC = 0
        activities = db.query(Activity).filter(
            and_(
                Activity.start_time >= start_date,
                Activity.start_time < end_date,
                (Activity.epoc.is_(None) | (Activity.epoc == 0))
            )
        ).order_by(Activity.start_time.desc()).all()
        
        print(f"📊 Fant {len(activities)} aktiviteter å beregne EPOC for")
        
        if not activities:
            print("✅ Ingen aktiviteter trenger EPOC-beregning")
            return
        
        # Grupper aktiviteter etter år for bedre oversikt
        activities_by_year = {}
        for activity in activities:
            year = activity.start_time.year
            if year not in activities_by_year:
                activities_by_year[year] = []
            activities_by_year[year].append(activity)
        
        print(f"\n📅 Aktivitetene fordelt på år:")
        for year in sorted(activities_by_year.keys(), reverse=True):
            print(f"   {year}: {len(activities_by_year[year])} aktiviteter")
        
        # Beregn EPOC for hver aktivitet
        updated_count = 0
        failed_count = 0
        
        for year in sorted(activities_by_year.keys(), reverse=True):
            year_activities = activities_by_year[year]
            print(f"\n🔢 Prosesserer {year} ({len(year_activities)} aktiviteter)")
            
            for i, activity in enumerate(year_activities, 1):
                try:
                    # Beregn EPOC
                    new_epoc = calculate_epoc_for_activity(activity)
                    
                    # Oppdater aktiviteten
                    activity.epoc = new_epoc
                    
                    # Vis fremdrift hver 10. aktivitet
                    if i % 10 == 0 or i == len(year_activities):
                        print(f"   {i:3d}/{len(year_activities)}: {activity.activity_name[:30]}... - EPOC: {new_epoc}")
                    
                    updated_count += 1
                    
                except Exception as e:
                    logger.error(f"Feil ved prosessering av aktivitet {activity.activity_id}: {e}")
                    failed_count += 1
                    continue
        
        # Lagre endringene til databasen
        print(f"\n💾 Lagrer endringer til database...")
        db.commit()
        
        print(f"\n✅ Fullført!")
        print(f"   Oppdatert: {updated_count} aktiviteter")
        print(f"   Feilet: {failed_count} aktiviteter")
        print(f"   Total prosessert: {len(activities)} aktiviteter")
        
        # Vis sammendrag av EPOC-verdier
        print(f"\n📊 SAMMENDRAG AV BEREGNETE EPOC-VERDIER:")
        
        # Hent noen eksempler på beregnede EPOC-verdier
        sample_activities = db.query(Activity).filter(
            and_(
                Activity.start_time >= start_date,
                Activity.start_time < end_date,
                Activity.epoc.isnot(None),
                Activity.epoc > 0
            )
        ).order_by(Activity.start_time.desc()).limit(10).all()
        
        for activity in sample_activities:
            print(f"  {activity.start_time.strftime('%Y-%m-%d')}: {activity.activity_name[:40]}... - EPOC: {activity.epoc}")
        
        # Vis statistikk
        epoc_stats = db.query(
            func.avg(Activity.epoc).label('avg_epoc'),
            func.min(Activity.epoc).label('min_epoc'),
            func.max(Activity.epoc).label('max_epoc'),
            func.count(Activity.epoc).label('count_epoc')
        ).filter(
            and_(
                Activity.start_time >= start_date,
                Activity.start_time < end_date,
                Activity.epoc.isnot(None),
                Activity.epoc > 0
            )
        ).first()
        
        if epoc_stats and epoc_stats.count_epoc > 0:
            print(f"\n📈 EPOC-STATISTIKK:")
            print(f"   Gjennomsnitt: {epoc_stats.avg_epoc:.1f}")
            print(f"   Minimum: {epoc_stats.min_epoc:.1f}")
            print(f"   Maksimum: {epoc_stats.max_epoc:.1f}")
            print(f"   Antall aktiviteter med EPOC: {epoc_stats.count_epoc}")
        
    except Exception as e:
        print(f"❌ Feil under EPOC-beregning: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    calculate_historical_epoc() 