#!/usr/bin/env python3
"""
Sjekk sleep scores i databasen
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from datetime import date
from app.database.session import SessionLocal
from app.database.models.sleep import Sleep

def check_sleep_scores():
    db = SessionLocal()
    
    # Hent søvndata for november 2025
    sleep_records = db.query(Sleep).filter(
        Sleep.sleep_date >= date(2025, 11, 1),
        Sleep.sleep_date <= date(2025, 11, 5)
    ).order_by(Sleep.sleep_date).all()
    
    print("\n=== Søvndata november 2025 ===\n")
    print(f"{'Dato':<12} {'Sleep Score':<15} {'Overall Score':<15} {'Sleep Time (h)':<15}")
    print("-" * 60)
    
    for sleep in sleep_records:
        sleep_hours = sleep.total_sleep_time / 3600 if sleep.total_sleep_time else 0
        print(f"{sleep.sleep_date!s:<12} {sleep.sleep_score or 'None':<15} {sleep.overall_score or 'None':<15} {sleep_hours:<15.1f}")
    
    db.close()

if __name__ == "__main__":
    check_sleep_scores()

