#!/usr/bin/env python3
"""Idempotent SQLite migration for activity weather enrichment columns."""

from __future__ import annotations

import logging
from pathlib import Path
import sys

from sqlalchemy import inspect, text

sys.path.append(str(Path(__file__).parent))

from app.database.session import engine

logger = logging.getLogger(__name__)


ACTIVITY_COLUMNS = {
    "wind_direction": "FLOAT",
}


def _add_column_if_missing(conn, table_name: str, column_name: str, column_type: str) -> None:
    inspector = inspect(conn)
    existing = {col["name"] for col in inspector.get_columns(table_name)}
    if column_name not in existing:
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))


def migrate_add_activity_weather() -> bool:
    try:
        with engine.begin() as conn:
            for column_name, column_type in ACTIVITY_COLUMNS.items():
                _add_column_if_missing(conn, "activities", column_name, column_type)
        return True
    except Exception as exc:
        logger.error("Activity weather-migrasjon feilet: %s", exc)
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ok = migrate_add_activity_weather()
    raise SystemExit(0 if ok else 1)
