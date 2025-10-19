#!/usr/bin/env python3
"""Sjekker antall aktiviteter i databasen"""

import sys
from pathlib import Path

# Legg til backend-katalogen i path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.database.session import SessionLocal
from app.database.models.activity import Activity

def main():
    db = SessionLocal()
    try:
        # Tell aktiviteter
        count = db.query(Activity).count()
        print(f'\nTotalt antall aktiviteter i databasen: {count}')
        
        # Finn eldste og nyeste
        earliest = db.query(Activity).order_by(Activity.start_time.asc()).first()
        latest = db.query(Activity).order_by(Activity.start_time.desc()).first()
        
        if earliest:
            print(f'Eldste aktivitet: {earliest.start_time.date()} - {earliest.activity_name}')
        if latest:
            print(f'Nyeste aktivitet: {latest.start_time.date()} - {latest.activity_name}')
            
        # Tell aktiviteter per år
        from sqlalchemy import func, extract
        year_counts = db.query(
            extract('year', Activity.start_time).label('year'),
            func.count(Activity.activity_id).label('count')
        ).group_by('year').order_by('year').all()
        
        print('\nAktiviteter per år:')
        for year, count in year_counts:
            print(f'  {int(year)}: {count} aktiviteter')
            
    finally:
        db.close()

if __name__ == '__main__':
    main()
