#!/usr/bin/env python3
import sys
from pathlib import Path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.database.session import SessionLocal
from app.database.models.summaries import MonthlySummary
import json

db = SessionLocal()
try:
    summary = db.query(MonthlySummary).filter_by(year=2024, month=11).first()
    if summary:
        print(f"Year-Month: {summary.year}-{summary.month}")
        print(f"activity_types_breakdown (raw): {summary.activity_types_breakdown}")
        if summary.activity_types_breakdown:
            try:
                breakdown = json.loads(summary.activity_types_breakdown) if isinstance(summary.activity_types_breakdown, str) else summary.activity_types_breakdown
                print(f"activity_types_breakdown (parsed):")
                for key, val in breakdown.items():
                    print(f"  {key}: {val}")
            except Exception as e:
                print(f"Error parsing: {e}")
finally:
    db.close()









