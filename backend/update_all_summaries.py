#!/usr/bin/env python3
"""
Skript for å oppdatere alle eksisterende sammendrag med ny duplikatfiltrering.
"""

from app.services.summary_service import SummaryService
from app.database.session import SessionLocal
from app.database.models.activity import Activity
from sqlalchemy import func, extract
from datetime import date, datetime

def update_all_summaries():
    """Oppdater alle eksisterende sammendrag med ny duplikatfiltrering."""
    print("Starter oppdatering av alle sammendrag med ny duplikatfiltrering...")
    
    db = SessionLocal()
    summary_service = SummaryService()
    
    try:
        # 1. Oppdater alle daglige sammendrag
        print("\n1. Oppdaterer daglige sammendrag...")
        daily_count = summary_service.calculate_daily_summaries()
        print(f"   ✓ {daily_count} daglige sammendrag oppdatert")
        
        # 2. Oppdater alle ukentlige sammendrag
        print("\n2. Oppdaterer ukentlige sammendrag...")
        weekly_count = summary_service.calculate_weekly_summaries()
        print(f"   ✓ {weekly_count} ukentlige sammendrag oppdatert")
        
        # 3. Oppdater alle månedlige sammendrag
        print("\n3. Oppdaterer månedlige sammendrag...")
        monthly_count = summary_service.calculate_monthly_summaries()
        print(f"   ✓ {monthly_count} månedlige sammendrag oppdatert")
        
        # 4. Vis statistikk over databasen
        print("\n4. Database-statistikk:")
        
        # Totalt antall aktiviteter
        total_activities = db.query(Activity).count()
        print(f"   Totalt antall aktiviteter: {total_activities}")
        
        # Unike activity_id
        unique_activity_ids = db.query(Activity.activity_id).distinct().count()
        print(f"   Unike activity_id: {unique_activity_ids}")
        
        # Datoer med aktiviteter
        dates_with_activities = db.query(func.date(Activity.start_time)).distinct().count()
        print(f"   Datoer med aktiviteter: {dates_with_activities}")
        
        # Uker med aktiviteter
        weeks_with_activities = db.query(
            extract('year', Activity.start_time).label('year'),
            extract('week', Activity.start_time).label('week')
        ).distinct().count()
        print(f"   Uker med aktiviteter: {weeks_with_activities}")
        
        # Måneder med aktiviteter
        months_with_activities = db.query(
            extract('year', Activity.start_time).label('year'),
            extract('month', Activity.start_time).label('month')
        ).distinct().count()
        print(f"   Måneder med aktiviteter: {months_with_activities}")
        
        # 5. Test en spesifikk periode
        print("\n5. Testing spesifikk periode (siste 7 dager):")
        
        end_date = date.today()
        start_date = end_date.replace(day=end_date.day - 7)
        
        # Hent aktiviteter for perioden
        period_activities = db.query(Activity).filter(
            func.date(Activity.start_time) >= start_date,
            func.date(Activity.start_time) <= end_date
        ).all()
        
        print(f"   Aktiviterer i perioden: {len(period_activities)}")
        
        # Sjekk for duplikater
        activity_ids = [a.activity_id for a in period_activities]
        unique_ids = set(activity_ids)
        duplicate_count = len(activity_ids) - len(unique_ids)
        
        print(f"   Unike activity_id: {len(unique_ids)}")
        print(f"   Duplikater: {duplicate_count}")
        
        # Oppdater sammendrag for perioden
        summary_service.bulk_update_summaries(start_date, end_date)
        print(f"   ✓ Sammendrag oppdatert for perioden {start_date} til {end_date}")
        
        print(f"\n=== OPPSUMERING ===")
        print(f"Daglige sammendrag oppdatert: {daily_count}")
        print(f"Ukentlige sammendrag oppdatert: {weekly_count}")
        print(f"Månedlige sammendrag oppdatert: {monthly_count}")
        print(f"Duplikater i testperiode: {duplicate_count}")
        
        if duplicate_count > 0:
            print(f"\n⚠️  {duplicate_count} duplikater funnet i testperioden!")
            print("   Sammendragene vil nå automatisk filtrere ut duplikater.")
        else:
            print(f"\n✓ Ingen duplikater funnet - sammendragene er oppdatert!")
        
    except Exception as e:
        print(f"✗ Oppdatering feilet: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    update_all_summaries() 