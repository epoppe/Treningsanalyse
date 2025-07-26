#!/usr/bin/env python3
"""
Script for å reberegne negative split for aktiviteter fra siste måned med ny logikk.
Ny logikk: negativ verdi = raskere andre halvdel (negativ split)
          positiv verdi = saktere andre halvdel (positiv split)
"""

import os
import sys
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, extract

# Legg til app-mappen i Python-stien
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.database.session import SessionLocal
from app.database.models.activity import Activity, ActivityType
from app.storage import DataStorage
from app.services.analysis_service import AnalysisService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_activities_from_last_month():
    """Henter alle løpeaktiviteter fra siste måned."""
    
    print("🔍 Henter løpeaktiviteter fra siste måned...")
    
    db = SessionLocal()
    try:
        # Hent ID for løpingstypen
        running_type = db.query(ActivityType).filter(ActivityType.type_key == 'running').first()
        if not running_type:
            print("❌ Aktivitetstypen 'running' ble ikke funnet")
            return []
        
        # Beregn datoer for siste måned
        today = datetime.now()
        first_day_last_month = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        last_day_last_month = today.replace(day=1) - timedelta(days=1)
        
        print(f"📅 Siste måned: {first_day_last_month.date()} til {last_day_last_month.date()}")
        
        # Hent aktiviteter fra siste måned
        activities = db.query(Activity).filter(
            and_(
                Activity.activity_type_id == running_type.id,
                Activity.start_time >= first_day_last_month,
                Activity.start_time <= last_day_last_month
            )
        ).all()
        
        print(f"✅ Fant {len(activities)} løpeaktiviteter fra siste måned")
        return activities
        
    except Exception as e:
        print(f"❌ Feil ved henting av aktiviteter: {e}")
        return []
    finally:
        db.close()

def recalculate_negative_split(activities):
    """Reberegner negative split for aktiviteter med ny logikk."""
    
    if not activities:
        print("❌ Ingen aktiviteter å prosessere")
        return
    
    print(f"\n🚀 Starter reberegning av negative split for {len(activities)} aktiviteter...")
    
    storage = DataStorage()
    analysis_service = AnalysisService(storage)
    db = SessionLocal()
    
    results = {
        'total_activities': len(activities),
        'recalculated': 0,
        'failed': 0,
        'no_fit_data': 0,
        'errors': []
    }
    
    try:
        for i, activity in enumerate(activities):
            activity_id = int(activity.activity_id)
            
            if i % 10 == 0:
                print(f"   Prosesserer aktivitet {i+1}/{len(activities)}: {activity_id}")
            
            try:
                # Sjekk om aktiviteten har FIT-data
                details_df = storage.get_activity_details(activity_id)
                if details_df is None or details_df.empty:
                    results['no_fit_data'] += 1
                    continue
                
                # Reberegn negative split med ny logikk
                result = analysis_service.calculate_negative_split(activity_id, db)
                
                if result:
                    results['recalculated'] += 1
                    old_value = activity.negative_split_percent
                    new_value = result['negative_split_percent']
                    print(f"   ✓ Aktivitet {activity_id}: {old_value:.2f}% → {new_value:.2f}%")
                else:
                    results['failed'] += 1
                    results['errors'].append(f"Aktivitet {activity_id}: Kunne ikke beregne")
                    
            except Exception as e:
                results['failed'] += 1
                error_msg = f"Aktivitet {activity_id}: {str(e)}"
                results['errors'].append(error_msg)
                print(f"   ❌ {error_msg}")
        
        return results
        
    except Exception as e:
        print(f"❌ Feil under reberegning: {e}")
        return results
    finally:
        db.close()

def print_results(results):
    """Skriver ut resultatene av reberegningen."""
    
    print(f"\n📊 RESULTATER AV REBEREGNING:")
    print(f"   Totalt antall aktiviteter: {results['total_activities']}")
    print(f"   Reberegnet: {results['recalculated']}")
    print(f"   Feilet: {results['failed']}")
    print(f"   Ingen FIT-data: {results['no_fit_data']}")
    print(f"   Suksessrate: {(results['recalculated'] / results['total_activities'] * 100):.1f}%")
    
    if results['errors']:
        print(f"\n❌ FEIL:")
        for error in results['errors'][:10]:  # Vis kun første 10 feil
            print(f"   - {error}")
        if len(results['errors']) > 10:
            print(f"   ... og {len(results['errors']) - 10} flere feil")

def main():
    """Hovedfunksjon."""
    
    print("🚀 STARTER REBEREGNING AV NEGATIVE SPLIT FOR SISTE MÅNED")
    print("=" * 60)
    print("Ny logikk: negativ verdi = raskere andre halvdel (negativ split)")
    print("          positiv verdi = saktere andre halvdel (positiv split)")
    print("=" * 60)
    
    # Steg 1: Hent aktiviteter fra siste måned
    activities = get_activities_from_last_month()
    
    if not activities:
        print("❌ Ingen aktiviteter funnet fra siste måned")
        return
    
    # Steg 2: Reberegn negative split
    results = recalculate_negative_split(activities)
    
    # Steg 3: Vis resultater
    print_results(results)
    
    print(f"\n✅ REBEREGNING FULLFØRT!")
    print(f"   Negative split er nå beregnet med ny logikk for aktiviteter fra siste måned")

if __name__ == "__main__":
    main() 