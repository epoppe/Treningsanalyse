#!/usr/bin/env python3
"""Migrerer databasen for å legge til Stress-tabell."""

import sys
from pathlib import Path

# Legg til backend-katalogen i Python-søkestien
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine, inspect
from app.config import settings
from app.database.models import Base, Stress

def migrate():
    """Kjor database-migrasjon."""
    print("[INFO] Starter migrasjon for Stress-tabell...")
    
    # Opprett database engine
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
    )
    
    # Sjekk om tabellen allerede eksisterer
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    
    if 'stress' in existing_tables:
        print("[OK] Stress-tabell eksisterer allerede!")
        return
    
    print("[INFO] Oppretter Stress-tabell...")
    
    # Opprett kun Stress-tabellen
    Stress.__table__.create(engine)
    
    print("[OK] Stress-tabell opprettet!")
    print("\nTabellen inneholder folgende kolonner:")
    print("  - id (primary key)")
    print("  - stress_date (unique, indexed)")
    print("  - stress_level")
    print("  - total_time")
    print("  - stress_time")
    print("  - rest_time")
    print("  - low_stress_time")
    print("  - medium_stress_time")
    print("  - high_stress_time")
    print("  - activity_stress_duration")
    print("  - data_quality")
    print("  - device_name")
    print("  - created_at")
    print("  - updated_at")
    print("  - detailed_stress_data (JSON)")
    
    print("\n[SUCCESS] Migrasjon fullfort!")

if __name__ == "__main__":
    migrate()

