#!/usr/bin/env python3
"""
Script for å beregne negative split og decoupling for alle aktiviteter som har FIT-data.
Dette scriptet vil:
1. Identifisere alle løpeaktiviteter tilbake til 2008
2. Sjekke hvilke som har FIT-data tilgjengelig
3. Beregne negative split og decoupling kun for de som har FIT-data
"""

import os
import sys
import pandas as pd
from datetime import datetime, date
from sqlalchemy.orm import Session
from sqlalchemy import and_, extract

# Legg til app-mappen i Python-stien
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.database.session import SessionLocal
from app.database.models.activity import Activity, ActivityType
from app.storage import DataStorage
from app.services.analysis_service import AnalysisService

def get_running_activities_with_fit_data():
    """Henter alle løpeaktiviteter som har FIT-data tilgjengelig."""
    
    print("🔍 Henter alle løpeaktiviteter fra database...")
    
    db = SessionLocal()
    try:
        # Hent alle løpeaktiviteter tilbake til 2008
        running_activities = db.query(Activity).join(ActivityType).filter(
            and_(
                ActivityType.type_key.in_(['running', 'trail_running', 'treadmill_running']),
                extract('year', Activity.start_time) >= 2008
            )
        ).order_by(Activity.start_time.desc()).all()
        
        print(f"📊 Fant {len(running_activities)} løpeaktiviteter fra 2008 og fremover")
        
        # Initialiser storage og analysis service
        storage = DataStorage()
        analysis_service = AnalysisService(storage)
        
        # Sjekk hvilke aktiviteter som har FIT-data
        activities_with_fit_data = []
        
        print("🔍 Sjekker hvilke aktiviteter som har FIT-data...")
        
        for i, activity in enumerate(running_activities):
            if i % 100 == 0:
                print(f"   Sjekker aktivitet {i+1}/{len(running_activities)}...")
            
            activity_id = int(activity.activity_id)
            
            # Sjekk om aktiviteten har FIT-data
            details_df = storage.get_activity_details(activity_id)
            
            if details_df is not None and not details_df.empty:
                # Sjekk at vi har nødvendige kolonner for beregninger
                has_speed = 'speed' in details_df.columns
                has_heart_rate = 'heart_rate' in details_df.columns
                has_timestamp = 'timestamp' in details_df.columns
                
                if has_speed and has_timestamp:  # Minimum for negative split
                    activities_with_fit_data.append({
                        'activity': activity,
                        'activity_id': activity_id,
                        'has_heart_rate': has_heart_rate,
                        'data_points': len(details_df),
                        'start_time': activity.start_time
                    })
        
        print(f"✅ Fant {len(activities_with_fit_data)} aktiviteter med FIT-data")
        
        return activities_with_fit_data, analysis_service, db
        
    except Exception as e:
        print(f"❌ Feil ved henting av aktiviteter: {e}")
        db.close()
        return [], None, None

def calculate_metrics_for_activities(activities_with_fit_data, analysis_service, db):
    """Beregner negative split og decoupling for aktiviteter med FIT-data."""
    
    if not activities_with_fit_data:
        print("❌ Ingen aktiviteter med FIT-data å beregne for")
        return
    
    print(f"\n🚀 Starter beregning av negative split og decoupling for {len(activities_with_fit_data)} aktiviteter...")
    
    results = {
        'total_activities': len(activities_with_fit_data),
        'negative_split_calculated': 0,
        'negative_split_cached': 0,
        'negative_split_failed': 0,
        'decoupling_calculated': 0,
        'decoupling_cached': 0,
        'decoupling_failed': 0,
        'activities_with_heart_rate': 0,
        'activities_without_heart_rate': 0
    }
    
    for i, activity_info in enumerate(activities_with_fit_data):
        activity = activity_info['activity']
        activity_id = activity_info['activity_id']
        has_heart_rate = activity_info['has_heart_rate']
        
        if i % 50 == 0:
            print(f"   Behandler aktivitet {i+1}/{len(activities_with_fit_data)}: {activity_id}")
        
        # Teller aktiviteter med/uten hjerterate
        if has_heart_rate:
            results['activities_with_heart_rate'] += 1
        else:
            results['activities_without_heart_rate'] += 1
        
        # Beregn negative split (krever kun speed og timestamp)
        try:
            negative_split_result = analysis_service.calculate_negative_split(activity_id, db)
            if negative_split_result:
                if negative_split_result.get('calculation_method') == 'calculated':
                    results['negative_split_calculated'] += 1
                else:
                    results['negative_split_cached'] += 1
            else:
                results['negative_split_failed'] += 1
        except Exception as e:
            print(f"   ⚠️  Feil ved negative split for aktivitet {activity_id}: {e}")
            results['negative_split_failed'] += 1
        
        # Beregn decoupling (krever heart_rate, speed og timestamp)
        if has_heart_rate:
            try:
                decoupling_result = analysis_service.calculate_decoupling(activity_id, db)
                if decoupling_result:
                    if decoupling_result.get('calculation_method') == 'calculated':
                        results['decoupling_calculated'] += 1
                    else:
                        results['decoupling_cached'] += 1
                else:
                    results['decoupling_failed'] += 1
            except Exception as e:
                print(f"   ⚠️  Feil ved decoupling for aktivitet {activity_id}: {e}")
                results['decoupling_failed'] += 1
        else:
            results['decoupling_failed'] += 1
    
    return results

def print_results(results):
    """Skriver ut resultatene av beregningene."""
    
    print(f"\n📊 RESULTATER:")
    print(f"   Totalt antall aktiviteter med FIT-data: {results['total_activities']}")
    print(f"   Aktiviter med hjerterate-data: {results['activities_with_heart_rate']}")
    print(f"   Aktiviter uten hjerterate-data: {results['activities_without_heart_rate']}")
    
    print(f"\n🎯 NEGATIVE SPLIT:")
    print(f"   Nylig beregnet: {results['negative_split_calculated']}")
    print(f"   Allerede cached: {results['negative_split_cached']}")
    print(f"   Feilet: {results['negative_split_failed']}")
    print(f"   Suksessrate: {((results['negative_split_calculated'] + results['negative_split_cached']) / results['total_activities'] * 100):.1f}%")
    
    print(f"\n💓 DECOUPLING:")
    print(f"   Nylig beregnet: {results['decoupling_calculated']}")
    print(f"   Allerede cached: {results['decoupling_cached']}")
    print(f"   Feilet: {results['decoupling_failed']}")
    print(f"   Suksessrate: {((results['decoupling_calculated'] + results['decoupling_cached']) / results['total_activities'] * 100):.1f}%")

def main():
    """Hovedfunksjon."""
    
    print("🚀 STARTER BEREGNING AV NEGATIVE SPLIT OG DECOUPLING")
    print("=" * 60)
    
    # Steg 1: Hent aktiviteter med FIT-data
    activities_with_fit_data, analysis_service, db = get_running_activities_with_fit_data()
    
    if not activities_with_fit_data:
        print("❌ Ingen aktiviteter med FIT-data funnet")
        return
    
    try:
        # Steg 2: Beregn metrics
        results = calculate_metrics_for_activities(activities_with_fit_data, analysis_service, db)
        
        # Steg 3: Vis resultater
        print_results(results)
        
        print(f"\n✅ BEREGNING FULLFØRT!")
        print(f"   Negative split og decoupling er nå tilgjengelig for aktiviteter med FIT-data")
        print(f"   API-endepunktene vil nå returnere beregnede verdier i stedet for 404")
        
    except Exception as e:
        print(f"❌ Feil under beregning: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        if db:
            db.close()

if __name__ == "__main__":
    main() 