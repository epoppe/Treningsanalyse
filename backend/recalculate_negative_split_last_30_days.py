#!/usr/bin/env python3
"""
Script for å reberegne negative split for aktiviteter fra siste 30 dager med ny logikk.
Ny logikk: negativ verdi = raskere andre halvdel (negativ split)
          positiv verdi = saktere andre halvdel (positiv split)
"""
import sys
import os
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Legg til backend-mappen i Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database.session import get_db
from app.database.models.activity import Activity, ActivityType
from app.services.analysis_service import AnalysisService
from app.storage import DataStorage
import logging

# Konfigurer logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_activities_last_30_days(db_session):
    """Hent alle aktiviteter fra siste 30 dager"""
    thirty_days_ago = datetime.now() - timedelta(days=30)
    
    activities = db_session.query(Activity).join(ActivityType).filter(
        ActivityType.type_key.in_(['running', 'treadmill_running', 'trail_running']),
        Activity.start_time >= thirty_days_ago
    ).order_by(Activity.start_time.desc()).all()
    
    return activities

def recalculate_negative_split(activities):
    """Reberegn negative split for alle aktiviteter"""
    print("🚀 STARTER REBEREGNING AV NEGATIVE SPLIT FOR SISTE 30 DAGER")
    print("=" * 60)
    print("Ny logikk: negativ verdi = raskere andre halvdel (negativ split)")
    print("          positiv verdi = saktere andre halvdel (positiv split)")
    print("=" * 60)
    
    # Initialiser services
    storage = DataStorage()
    analysis_service = AnalysisService(storage)
    
    # Hent database session
    db = next(get_db())
    
    total_activities = len(activities)
    recalculated = 0
    failed = 0
    no_fit_data = 0
    corrected = 0
    
    print(f"🔍 Fant {total_activities} løpeaktiviteter fra siste 30 dager")
    print(f"🚀 Starter reberegning av negative split for {total_activities} aktiviteter...")
    
    try:
        for i, activity in enumerate(activities, 1):
            activity_id = int(activity.activity_id)
            activity_date = activity.start_time.strftime("%Y-%m-%d %H:%M")
            old_value = activity.negative_split_percent
            
            print(f"   Prosesserer aktivitet {i}/{total_activities}: {activity_id}")
            
            # Sjekk om aktiviteten har FIT-data
            fit_data = storage.get_activity_details(activity_id)
            if fit_data is None or len(fit_data) == 0:
                print(f"   ⚠️  Aktivitet {activity_id}: Ingen FIT-data")
                no_fit_data += 1
                continue
            
            try:
                # Nullstill cached verdi for å tvinge ny beregning
                activity.negative_split_percent = None
                db.commit()
                
                # Beregn negative split med ny logikk
                result = analysis_service.calculate_negative_split(activity_id, db)
                
                if result and 'negative_split_percent' in result:
                    new_value = result['negative_split_percent']
                    
                    # Sjekk om verdien endret seg
                    if old_value != new_value:
                        print(f"   ✅ Aktivitet {activity_id}: {old_value:.2f}% → {new_value:.2f}% (KORRIGERT)")
                        corrected += 1
                    else:
                        print(f"   ✓ Aktivitet {activity_id}: {old_value:.2f}% → {new_value:.2f}% (samme)")
                    
                    recalculated += 1
                else:
                    print(f"   ❌ Aktivitet {activity_id}: Kunne ikke beregne negative split")
                    failed += 1
                    
            except Exception as e:
                print(f"   ❌ Aktivitet {activity_id}: Feil - {str(e)}")
                failed += 1
                
    except Exception as e:
        print(f"❌ Feil under reberegning: {e}")
        logger.error(f"Feil under reberegning av negative split: {e}")
    finally:
        db.close()
    
    # Vis resultater
    print("\n📊 RESULTATER AV REBEREGNING:")
    print(f"   Totalt antall aktiviteter: {total_activities}")
    print(f"   Reberegnet: {recalculated}")
    print(f"   Korrigert: {corrected}")
    print(f"   Feilet: {failed}")
    print(f"   Ingen FIT-data: {no_fit_data}")
    
    if total_activities > 0:
        success_rate = (recalculated / total_activities) * 100
        print(f"   Suksessrate: {success_rate:.1f}%")
    
    print("✅ REBEREGNING FULLFØRT!")
    print("   Negative split er nå beregnet med ny logikk for aktiviteter fra siste 30 dager")

def main():
    """Hovedfunksjon"""
    try:
        # Hent database session
        db = next(get_db())
        
        # Hent aktiviteter fra siste 30 dager
        activities = get_activities_last_30_days(db)
        
        if not activities:
            print("❌ Ingen aktiviteter funnet fra siste 30 dager")
            return
        
        # Reberegn negative split
        recalculate_negative_split(activities)
        
    except Exception as e:
        print(f"❌ Feil: {e}")
        logger.error(f"Feil i hovedfunksjon: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    main() 