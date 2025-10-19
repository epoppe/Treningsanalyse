#!/usr/bin/env python3
import sys
from pathlib import Path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.database.session import SessionLocal
from app.database.models.summaries import MonthlySummary
from app.services.summary_service import SummaryService

db = SessionLocal()
try:
    # Slett november 2024
    db.query(MonthlySummary).filter_by(year=2024, month=11).delete()
    db.commit()
    print("Slettet november 2024")
    
    # Regenerer
    service = SummaryService()
    summary = service.calculate_monthly_summary(2024, 11)
    if summary:
        print(f"Regenerert: {summary.activity_types_breakdown}")
    else:
        print("Ingen aktiviteter funnet")
finally:
    db.close()



