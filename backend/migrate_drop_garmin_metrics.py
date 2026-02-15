#!/usr/bin/env python3
"""Fjerner garmin_metrics-tabellen fra databasen."""

import sys
from pathlib import Path

backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine, inspect, text
from app.config import settings


def migrate():
    """Kjør migrasjon for å fjerne garmin_metrics-tabellen."""
    print("[INFO] Fjerner garmin_metrics-tabellen...")

    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
    )

    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    if "garmin_metrics" not in existing_tables:
        print("[OK] garmin_metrics-tabellen finnes ikke - ingenting å fjerne.")
        return

    with engine.connect() as conn:
        conn.execute(text("DROP TABLE garmin_metrics"))
        conn.commit()

    # Fjern sync_state for garmin_metrics
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM sync_state WHERE key = 'garmin_metrics'"))
        conn.commit()

    print("[OK] garmin_metrics-tabellen fjernet.")


if __name__ == "__main__":
    migrate()
