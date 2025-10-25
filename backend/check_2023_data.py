#!/usr/bin/env python3
import sys
from pathlib import Path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.database.session import SessionLocal
from app.database.models.summaries import MonthlySummary
from app.database.models.activity import Activity
from sqlalchemy import and_, extract

db = SessionLocal()
try:
    # Sjekk om det finnes sammendrag for 2023
    summaries_2023 = db.query(MonthlySummary).filter(MonthlySummary.year == 2023).count()
    print(f"Antall månedlige sammendrag for 2023: {summaries_2023}")
    
    # Sjekk om det finnes aktiviteter for 2023
    activities_2023 = db.query(Activity).filter(
        extract('year', Activity.start_time) == 2023
    ).count()
    print(f"Antall aktiviteter for 2023: {activities_2023}")
    
    # Sjekk november 2023
    nov23 = db.query(MonthlySummary).filter_by(year=2023, month=11).first()
    if nov23:
        print(f"\nNovember 2023 finnes:")
        print(f"  total_distance: {nov23.total_distance/1000:.1f} km")
        print(f"  total_activities: {nov23.total_activities}")
        print(f"  activity_types_breakdown: {nov23.activity_types_breakdown[:150] if nov23.activity_types_breakdown else 'None'}...")
    else:
        print("\nNovember 2023 finnes IKKE i MonthlySummary")
    
finally:
    db.close()




