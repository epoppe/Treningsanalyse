#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.database.session import SessionLocal
from app.services.summary_service import SummaryService

db = SessionLocal()
try:
    service = SummaryService()
    
    # Regenerer alle månedlige sammendrag
    print("Regenererer alle månedlige sammendrag...")
    count = service.calculate_monthly_summaries()
    print(f"Oppdatert {count} månedlige sammendrag")
    
    # Sjekk november 2025
    from app.database.models.summaries import MonthlySummary
    summary = db.query(MonthlySummary).filter_by(year=2025, month=11).first()
    if summary:
        print(f"\nNovember 2025:")
        print(f"  Total aktiviteter: {summary.total_activities}")
        print(f"  Total TSS: {summary.total_tss}")
        print(f"  Total kalorier: {summary.total_calories}")
        
finally:
    db.close()
    if hasattr(service, 'db'):
        service.db.close()

