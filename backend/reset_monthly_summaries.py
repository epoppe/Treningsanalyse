#!/usr/bin/env python3
"""Slett alle månedlige sammendrag slik at de kan regenereres"""
import sys
from pathlib import Path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.database.session import SessionLocal
from app.database.models.summaries import MonthlySummary

db = SessionLocal()
try:
    count = db.query(MonthlySummary).count()
    print(f"Sletter {count} månedlige sammendrag...")
    db.query(MonthlySummary).delete()
    db.commit()
    print("Ferdig!")
finally:
    db.close()




