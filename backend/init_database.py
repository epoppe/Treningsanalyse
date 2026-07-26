#!/usr/bin/env python3
"""
Database initialization via Alembic migrations.

Bruk:
    python init_database.py
    # eller direkte:
    alembic upgrade head
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

from app.config import settings
from app.database.session import engine, SessionLocal
from app.database.migrations import run_migrations
from app.database.models.activity import ActivityType


def seed_default_activity_types() -> None:
    """Legg til standard aktivitetstyper hvis tabellen er tom."""
    db = SessionLocal()
    try:
        existing_types = db.query(ActivityType).count()
        if existing_types > 0:
            print(f"✓ Activity types already exist ({existing_types} types)")
            return

        print("Adding default activity types...")
        default_types = [
            {"type_key": "running", "type_name": "Løping", "parent_type_key": None},
            {"type_key": "cycling", "type_name": "Sykling", "parent_type_key": None},
            {"type_key": "swimming", "type_name": "Svømming", "parent_type_key": None},
            {"type_key": "walking", "type_name": "Gåing", "parent_type_key": None},
            {"type_key": "hiking", "type_name": "Fotturer", "parent_type_key": "walking"},
            {"type_key": "strength_training", "type_name": "Styrketrening", "parent_type_key": None},
            {"type_key": "yoga", "type_name": "Yoga", "parent_type_key": None},
            {"type_key": "other", "type_name": "Annet", "parent_type_key": None},
        ]
        for activity_type_data in default_types:
            db.add(ActivityType(**activity_type_data))
        db.commit()
        print("✓ Default activity types added")
    except Exception as exc:
        print(f"Error adding activity types: {exc}")
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    print("Initializing database via Alembic...")
    print("=" * 50)
    try:
        revision = run_migrations(engine, settings.DATABASE_URL)
        print(f"✓ Schema migrated to revision {revision}")
        seed_default_activity_types()
        print("\n" + "=" * 50)
        print("Database initialization completed successfully!")
    except Exception as exc:
        print(f"Database initialization failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
