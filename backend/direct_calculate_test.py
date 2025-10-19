#!/usr/bin/env python3
"""Test calculate_monthly_summary direkte"""
import sys
from pathlib import Path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.database.session import SessionLocal
from app.database.models.summaries import MonthlySummary
from app.services.summary_service import SummaryService
import json

# Slett november 2024
db = SessionLocal()
try:
    print("Sletter november 2024...")
    db.query(MonthlySummary).filter_by(year=2024, month=11).delete()
    db.commit()
    db.close()
    
    # Opprett ny service instance og beregn
    print("Oppretter ny SummaryService...")
    service = SummaryService()
    
    print("Beregner november 2024...")
    summary = service.calculate_monthly_summary(2024, 11)
    
    if summary:
        print(f"\nSUCCESS!")
        print(f"activity_types_breakdown (raw): {summary.activity_types_breakdown}")
        
        if summary.activity_types_breakdown:
            try:
                breakdown = json.loads(summary.activity_types_breakdown) if isinstance(summary.activity_types_breakdown, str) else summary.activity_types_breakdown
                print(f"\nParsed breakdown:")
                for key, val in breakdown.items():
                    print(f"  {key}: count={val.get('count')}, distance={val.get('distance', 0)/1000:.1f} km")
            except Exception as e:
                print(f"Error parsing: {e}")
    else:
        print("FAILED: No summary returned")
        
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
finally:
    # Lukk service sin db-connection
    if 'service' in locals():
        service.db.close()



