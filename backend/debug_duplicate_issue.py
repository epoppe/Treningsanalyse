#!/usr/bin/env python3
"""
Debug-skript for å undersøke duplikatproblemet i sammendrag.
"""

from datetime import date, datetime
from app.services.summary_service import SummaryService
from app.database.session import SessionLocal
from app.database.models.activity import Activity
from sqlalchemy import func
from collections import Counter

def debug_duplicate_issue():
    """Undersøk duplikatproblemet i sammendrag."""
    print("Debugging duplikatproblemet i sammendrag...")
    
    db = SessionLocal()
    summary_service = SummaryService()
    
    try:
        # Test en spesifikk dag (16.7.2025 fra skjermbildet)
        test_date = date(2025, 7, 16)
        print(f"\n1. Testing dag: {test_date}")
        
        # Hent alle aktiviteter for denne dagen
        activities = db.query(Activity).filter(
            func.date(Activity.start_time) == test_date
        ).all()
        
        print(f"   Totalt antall aktiviteter i databasen: {len(activities)}")
        
        # Vis detaljer for hver aktivitet
        for i, activity in enumerate(activities):
            print(f"   Aktivitet {i+1}:")
            print(f"     Activity ID: {activity.activity_id}")
            print(f"     Navn: {activity.activity_name}")
            print(f"     Starttid: {activity.start_time}")
            print(f"     Type: {activity.activity_type.type_name if activity.activity_type else 'Ukjent'}")
            print(f"     Distanse: {activity.distance}m")
            print(f"     Varighet: {activity.duration}s")
            print()
        
        # Sjekk for duplikater basert på activity_id
        activity_ids = [a.activity_id for a in activities]
        unique_ids = set(activity_ids)
        duplicate_count = len(activity_ids) - len(unique_ids)
        
        print(f"   Unike activity_id: {len(unique_ids)}")
        print(f"   Duplikater funnet: {duplicate_count}")
        
        if duplicate_count > 0:
            counter = Counter(activity_ids)
            duplicates = [aid for aid, count in counter.items() if count > 1]
            print(f"   Duplikat activity_id: {duplicates}")
            
            # Vis detaljer for duplikater
            for dup_id in duplicates:
                dup_activities = [a for a in activities if a.activity_id == dup_id]
                print(f"     Activity {dup_id}: {len(dup_activities)} kopier")
                for i, act in enumerate(dup_activities):
                    print(f"       Kopi {i+1}: Activity ID={act.activity_id}, start_time={act.start_time}, name='{act.activity_name}'")
        
        # Test sammendrag-beregning
        print(f"\n2. Testing sammendrag-beregning:")
        summary = summary_service.calculate_daily_summary(test_date)
        if summary:
            print(f"   Sammendrag total_activities: {summary.total_activities}")
            print(f"   Forventet (unike): {len(unique_ids)}")
            print(f"   ✓ Sammendrag bruker unike aktiviteter: {summary.total_activities == len(unique_ids)}")
            
            # Vis sammendrag-detaljer
            print(f"   Sammendrag-detaljer:")
            print(f"     Total distanse: {summary.total_distance}m")
            print(f"     Total varighet: {summary.total_duration}s")
            print(f"     Total kalorier: {summary.total_calories}")
        else:
            print("   Ingen sammendrag generert")
        
        # Test en annen dag (14.7.2025)
        test_date2 = date(2025, 7, 14)
        print(f"\n3. Testing dag: {test_date2}")
        
        activities2 = db.query(Activity).filter(
            func.date(Activity.start_time) == test_date2
        ).all()
        
        print(f"   Totalt antall aktiviteter: {len(activities2)}")
        
        activity_ids2 = [a.activity_id for a in activities2]
        unique_ids2 = set(activity_ids2)
        duplicate_count2 = len(activity_ids2) - len(unique_ids2)
        
        print(f"   Unike activity_id: {len(unique_ids2)}")
        print(f"   Duplikater funnet: {duplicate_count2}")
        
        # Test sammendrag-beregning for dag 2
        summary2 = summary_service.calculate_daily_summary(test_date2)
        if summary2:
            print(f"   Sammendrag total_activities: {summary2.total_activities}")
            print(f"   Forventet (unike): {len(unique_ids2)}")
            print(f"   ✓ Sammendrag bruker unike aktiviteter: {summary2.total_activities == len(unique_ids2)}")
        
        # Test siste 7 dager for å se om problemet er konsistent
        print(f"\n4. Testing siste 7 dager:")
        from datetime import timedelta
        end_date = date.today()
        start_date = end_date - timedelta(days=7)
        
        for i in range(7):
            test_day = start_date + timedelta(days=i)
            day_activities = db.query(Activity).filter(
                func.date(Activity.start_time) == test_day
            ).all()
            
            if day_activities:
                day_activity_ids = [a.activity_id for a in day_activities]
                day_unique_ids = set(day_activity_ids)
                day_duplicate_count = len(day_activity_ids) - len(day_unique_ids)
                
                print(f"   {test_day}: {len(day_activities)} aktiviteter, {len(day_unique_ids)} unike, {day_duplicate_count} duplikater")
                
                if day_duplicate_count > 0:
                    print(f"     ⚠️  Duplikater funnet!")
        
        print(f"\n=== KONKLUSJON ===")
        if duplicate_count > 0 or duplicate_count2 > 0:
            print(f"⚠️  Duplikater funnet i databasen!")
            print(f"   Dette forklarer hvorfor sammendragene teller flere ganger.")
        else:
            print(f"✓ Ingen duplikater funnet i databasen.")
            print(f"   Hvis sammendragene fortsatt teller feil, kan problemet være:")
            print(f"   1. Frontend-caching av gamle data")
            print(f"   2. API-endepunkter som ikke bruker oppdaterte sammendrag")
            print(f"   3. Feil i sammendrag-beregningslogikken")
        
    except Exception as e:
        print(f"✗ Debug feilet: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    debug_duplicate_issue() 